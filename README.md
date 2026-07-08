# AI Recipe Masterclass

A recipe generation system combining a fine-tuned LLM with a retrieval-augmented
generation (RAG) pipeline, deployed as containerized microservices.

## Architecture

**Fine-tuned model** — Qwen2.5-7B-Instruct fine-tuned on recipe data
(`src/notebooks/cluster_finetuner.py`, run on a SLURM cluster), converted to GGUF and
served via Ollama as `toriko3`.

**RAG pipeline** (`src/rag/`) — augments the fine-tuned model with cuisine coverage it
doesn't have on its own (African, Scandinavian, Indian dishes), grounding answers in a
curated + web-sourced recipe corpus (~20,000 recipes) instead of relying purely on what
the model memorized during training. Retrieval is hybrid (BM25 + dense embeddings via
`BAAI/bge-base-en-v1.5`, fused with Reciprocal Rank Fusion) and reranked with a
cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) before grounding a response.

**Production deployment** — split into two services so the orchestration layer can grow
(query rewriting, discount-driven recipe generation, etc.) without touching retrieval
internals:

- `rag-service` — retrieval only (embedder, Qdrant client, BM25, reranker). Internal-only,
  never exposed publicly.
- `pipeline-service` — thin orchestrator. Calls `rag-service` for grounding context, then
  calls Ollama directly (colocated on the same machine) to generate the answer. This is
  the service exposed publicly.
- `qdrant` — vector database, Docker, localhost-only.

All three run via `docker-compose.yml` on a Mac mini alongside Ollama, exposed through a
Cloudflare Tunnel at `recipe.bebs.dev` — no public inbound ports needed.

```
Client → recipe.bebs.dev (Cloudflare Tunnel)
              │
              ▼
       pipeline-service ──→ rag-service ──→ qdrant
              │
              ▼
        Ollama (native, same host)
```

## Repository layout

```
src/
  notebooks/          fine-tuning scripts + recipe corpus data
    cluster_finetuner.py       SLURM fine-tuning entrypoint
    build_recipe_corpus.py     builds web_recipe_corpus.json from food.com/Kaggle/Indian datasets
    synthetic_*.json           curated recipe corpora (African, Scandinavian)
  rag/
    config.py                  single source of truth for all pipeline settings
    embedder.py                 sentence-transformers wrapper (bge-base)
    vector_database.py          Qdrant client (local embedded mode or server mode)
    hybrid_retriever.py          BM25 + dense retrieval with RRF fusion
    reranker.py                  cross-encoder reranking
    query_normalizer.py          typo correction against corpus vocabulary
    recipe_loader.py             loads recipe JSON sources into embeddable chunks
    country_demonyms.py          country → demonym mapping (BM25 has no stemming)
    generator.py                 LLM client (Ollama native or OpenWebUI)
    pipeline.py                  RecipeRAGPipeline — retrieval + generation orchestration
    retrieval_server.py          FastAPI app for rag-service
    pipeline_server.py           FastAPI app for pipeline-service
    retrieval_client.py          HTTP client pipeline-service uses to reach rag-service
    grocery_discounts.py         Kassalapp client + discount-detection logic (v2)
    discounts_store.py           SQLite cache /recipes/discounted reads from
    refresh_discounts.py         cron entrypoint that populates the cache above
    cli.py                       interactive CLI for local development
    run_eval.py                  retrieval regression suite (eval_set.json)
    tests/                       unit tests (pytest)
    Dockerfile.retrieval         rag-service image
    Dockerfile.pipeline          pipeline-service image
  docker-compose.yml            full production stack (qdrant + rag-service + pipeline-service)
mobile-app/                     React Native (Expo) client — see mobile-app/README.md
```

## Running locally

```bash
cd src
pip install -r rag/requirements-retrieval.txt -r rag/requirements-pipeline.txt
python -m rag.cli "norwegian ribbe"          # single query
python -m rag.cli                            # interactive loop
python -m rag.cli --rebuild                  # force re-embed the corpus
python -m rag.run_eval                       # retrieval regression check
python -m pytest rag/tests/                  # unit tests
```

By default this uses local embedded Qdrant (file-based) and talks to the LLM via
OpenWebUI. Set `QDRANT_URL` and `LLM_API_STYLE=ollama` + `OLLAMA_BASE_URL` (see
`rag/config.py`) to point at a different backend.

Secrets (`OLLAMA_API_KEY`) live in `src/rag/.env`, which is gitignored — create your own
from `rag/config.py`'s expected environment variables.

## Deploying

```bash
cd src
docker compose up -d --build
```

Requires `QDRANT_URL`, `LLM_API_STYLE=ollama`, and `OLLAMA_BASE_URL` set via the
compose file's environment (already configured for a colocated Ollama instance at
`host.docker.internal:11434`). See `docker-compose.yml` for the full service
definitions, including the volume mounts needed to persist the embedding manifest and
HuggingFace model cache across container restarts (without them, every restart
re-embeds the full ~20k-recipe corpus from scratch).

## API

`pipeline-service` exposes:

- `POST /query` — ask a question, get a grounded (or best-effort) answer
- `POST /query/stream` — same, streamed via SSE
- `POST /recipes/from-ingredients` — given a list of ingredients, returns up to
  `max_results` matching corpus recipes, or several LLM-generated suggestions if nothing
  in the corpus matches
- `GET /recipes/discounted` — v2: reads the cached Kassalapp discount scan (see "Grocery
  discount caching" below — not a live Kassalapp call per request) and, unless
  `include_recipes=false`, feeds the discovered product names into the same
  corpus-first/LLM-fallback logic as `/recipes/from-ingredients` (see
  `rag/grocery_discounts.py` for why product names, not the originally-intended
  ingredient label, are what get passed through). Response includes `updated_at` (when
  the cache was last refreshed). Returns `{"error": "KASSALAPP_API_KEY not configured"}`
  until a key is set
- `GET /health`

`rag-service` exposes `POST /retrieve` and `GET /health`, reachable only from
`pipeline-service` over the internal Docker network.

## Grocery discount caching

Kassalapp's underlying grocery offers refresh roughly weekly (like any Norwegian
"kundeavis"), not per-request, and there's no webhook to react to when they change (no
"on sale" or "has this changed" endpoint exists — confirmed against the docs). Scanning
live on every `/recipes/discounted` hit was needless load against Kassalapp's rate limits
for data that's already stale by the next request — confirmed live: a handful of manual
test calls in quick succession was enough to get 429'd partway through a scan.

Instead, `rag/discounts_store.py` is a small SQLite cache (one table, replaced wholesale
on each scan — see the module docstring for why a plain relational table beats a JSON
blob here) that `pipeline_server.py` only ever reads from. The only writer is
`rag/refresh_discounts.py`, triggered by a host cron job:

```
0 5 * * * cd ~/recipe-rag && docker compose exec -T pipeline-service python -m rag.refresh_discounts >> ~/recipe-rag/discount-refresh.log 2>&1
```

Runs daily rather than trying to guess which day each chain refreshes its own offers
(varies by chain) — cheap enough to run that often (one scan takes well under a minute).
The cache lives in a bind-mounted volume (`./discounts_cache` in `docker-compose.yml`) so
it survives container rebuilds/redeploys. Deliberately **not** exposed as a public HTTP
endpoint to trigger on demand — that would let anything external repeatedly burn
Kassalapp's rate limit; refreshing is cron/SSH-only.

## Status

- ✅ Fine-tuned model + RAG pipeline live at `recipe.bebs.dev`
- ✅ 20,217-recipe corpus (food.com + Kaggle + Indian dataset + curated African +
  Scandinavian recipes), full retrieval regression suite passing
- ✅ v2 discount-driven recipe generation — live at `recipe.bebs.dev/recipes/discounted`.
  Sweeps a curated list of ~30 grocery categories (`FOOD_CATEGORIES` in
  `grocery_discounts.py`, chosen against Kassalapp's ~2,000-category taxonomy — free-text
  search alone surfaced baby food for common terms like "kylling"/chicken) and evaluates
  *every* product each category returns for a discount, not one hand-picked
  representative per ingredient — batching each category's candidates into a single
  price-history lookup so this broader coverage costs the same Kassalapp API budget as
  the old one-representative-per-ingredient design. Confirmed live that the
  `price_history` embedded in `/products` search results spans wildly inconsistent, often
  stale date ranges, so a discount is always computed from a separate `prices-bulk` call
  instead, never that embedded field. The pipeline passes whatever real product a
  category search finds straight to the LLM and trusts it to interpret correctly —
  confirmed live that this works well (a mismatched "ham" result under an "eggs" search
  still produced a correct ham suggestion, never a hallucinated egg dish). Run
  `python -m rag.grocery_discounts` to sanity-check current lookups against the live API.
- ✅ Discount scan is cached (SQLite) and refreshed daily via cron, not scanned live per
  request — see "Grocery discount caching" above. Captures store name/logo and product
  image per discount, not just price, for the mobile app's Mattilbud-style deal cards.
- ✅ React Native mobile app (`mobile-app/`) — Tilbud (deals, grouped by store) as the
  home tab, plus Ask and Ingredients. Tapping a deal generates a recipe for that one
  product on demand rather than generating for the whole list up front.
- ⏳ v2 reverse ingredient-sourcing (given a recipe, find where to buy ingredients
  cheapest) — not yet built

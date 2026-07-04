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
    cli.py                       interactive CLI for local development
    run_eval.py                  retrieval regression suite (eval_set.json)
    tests/                       unit tests (pytest)
    Dockerfile.retrieval         rag-service image
    Dockerfile.pipeline          pipeline-service image
  docker-compose.yml            full production stack (qdrant + rag-service + pipeline-service)
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
- `GET /health`

`rag-service` exposes `POST /retrieve` and `GET /health`, reachable only from
`pipeline-service` over the internal Docker network.

## Status

- ✅ Fine-tuned model + RAG pipeline live at `recipe.bebs.dev`
- ✅ 20,217-recipe corpus (food.com + Kaggle + Indian dataset + curated African +
  Scandinavian recipes), full retrieval regression suite passing
- ⏳ v2: discount-driven recipe generation (pull grocery deals, generate recipes from
  what's on sale) and reverse ingredient-sourcing (given a recipe, find where to buy
  ingredients cheapest) — not yet built

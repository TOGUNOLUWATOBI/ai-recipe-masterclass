"""Recipe RAG pipeline: retrieve a matching curated recipe (if one exists) and ground
the fine-tuned model's answer in it, instead of relying purely on what got baked into
the model's weights during training.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

from .config import RecipeRAGConfig

# Imported lazily inside find_recipes_from_ingredients()/find_recipes_or_generate()
# instead of at module level: grocery_terms.py pulls in grocery_discounts.py, which
# needs `requests` -- a dependency the retrieval-service half of the split deployment
# deliberately does not install (see requirements-retrieval.txt), even though
# retrieval_server.py imports this whole module (see the TYPE_CHECKING comment below
# for the same rag-service/pipeline-service dependency split this follows). A
# top-level import here would break that container at startup.

# Only imported for type hints, not at runtime — build_index() and initialize_generator()
# do these imports lazily so each half of the split deployment only pulls in the
# dependencies it actually needs: rag-service (retrieval, build_index()) never needs
# requests/ollama, and pipeline-service (generation, build_index_remote()) never needs
# torch/sentence-transformers/qdrant-client/rank-bm25.
if TYPE_CHECKING:
    from .embedder import TextEmbedder
    from .generator import RecipeGenerator
    from .hybrid_retriever import HybridRetriever
    from .vector_database import QdrantVectorDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Same strict formatting/no-hallucination rules as the Ollama Modelfile, plus explicit
# instructions on how to use retrieved reference recipes — keeps the fine-tuned model's
# output style consistent whether or not retrieval found a match for this dish.
SYSTEM_PROMPT = """You are a master chef and a strictly professional culinary assistant.
Your goal is to provide accurate, delicious, and easy-to-follow recipes.

STRICT FORMATTING RULES:
1. NEVER use R-programming syntax (like c(), quotes, or brackets around lists).
2. Ingredients must be presented as a simple, clean bulleted list.
3. Instructions must be a numbered list of clear, concise steps.
4. If you do not have a specific ingredient for a dish, suggest a common substitute instead of hallucinating.
5. Do not include conversational filler unless asked.
6. Use only standard, plain English text.

USING REFERENCE RECIPES:
- If a reference recipe below matches the dish being asked about, treat it as ground truth for
  ingredients and technique — do not deviate from it or substitute in a different cuisine's methods.
- If no reference recipe matches the request, answer from your own knowledge as usual, following
  the same formatting rules above.
- Never mention "the reference recipe," "the context," or that you were given supporting material —
  just answer as the chef."""


def _point_id(source_file: str, chunk_id) -> str:
    """Stable Qdrant point ID for a chunk, derived from its natural composite key
    (source_file, chunk_id) rather than its position in whatever order the corpus
    happens to load in — the same recipe always maps to the same point across runs,
    regardless of what else gets added/removed/reordered around it elsewhere in the
    corpus. This is what makes true incremental indexing possible: without a stable
    id, there'd be no way to tell "chunk 47 in today's load" apart from "chunk 47 in
    yesterday's load" once the underlying list of recipes has changed shape. uuid5
    (not uuid4) so this is deterministic — same input always produces the same UUID,
    no randomness — and qdrant-client's PointStruct accepts UUID strings as ids."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{source_file}::{chunk_id}"))


def _chunk_hash(chunk: Dict[str, Any], embedding_model: str) -> str:
    """Per-chunk analogue of the old whole-corpus content hash: sha256 of just this
    chunk's own text + the embedding model, so build_index() can tell exactly which
    individual chunks changed instead of only knowing *that* something, somewhere in
    the corpus, changed — the same "hash content + embedding model, not just a count"
    principle as before (a count-only or single-combined-hash check would silently
    keep serving stale embeddings for one edited recipe, or force a full re-embed of
    everything for that same single edit), just scoped down to one chunk so only the
    chunks that actually changed need re-embedding."""
    hasher = hashlib.sha256()
    hasher.update(embedding_model.encode("utf-8"))
    hasher.update(chunk["text"].encode("utf-8"))
    return hasher.hexdigest()


def _doc_from_chunk(chunk: Dict[str, Any], point_id: str, embedding) -> Dict[str, Any]:
    """Builds the {id, embedding, text, metadata} shape QdrantVectorDB.index_documents()
    expects, keyed on the chunk's stable point_id rather than its position in whatever
    list it's being embedded from — the full corpus during a one-time migration/full
    rebuild, or just the new/changed subset during an incremental update."""
    return {
        "id": point_id,
        "embedding": embedding,
        "text": chunk["text"],
        "metadata": {
            "title": chunk["title"],
            "source_file": chunk["source_file"],
            "chunk_id": chunk["chunk_id"],
        },
    }


def _write_manifest(manifest_path: Path, embedding_model: str, chunk_map: Dict[str, str]) -> None:
    """New-format manifest: embedding_model + every currently-indexed chunk's
    point_id -> chunk_hash, so the next build_index() call can diff against it to
    find exactly what's new, changed, or removed — instead of the old format's single
    whole-corpus content_hash, which could only say "something changed" and had no
    way to say what."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "embedding_model": embedding_model,
        "chunks": chunk_map,
    }))


def _split_generated_recipes(text: str) -> List[Dict[str, str]]:
    """Splits a multi-recipe LLM completion ("### Title\n...### Title\n...") into
    separate recipe dicts, so the generated-fallback branch of find_recipes_or_generate()
    returns a list matching the corpus branch's shape instead of one undifferentiated
    blob — same "### Title" convention the corpus recipes and SYSTEM_PROMPT already use."""
    blocks = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    recipes = []
    for block in blocks:
        block = block.strip()
        if not block.startswith("### "):
            continue
        title = block.split("\n", 1)[0][len("### "):].strip()
        recipes.append({"title": title, "text": block})
    return recipes


class RecipeRAGPipeline:
    def __init__(self, config: Optional[RecipeRAGConfig] = None):
        self.config = config or RecipeRAGConfig()
        self.embedder: "Optional[TextEmbedder]" = None
        self.vector_db: "Optional[QdrantVectorDB]" = None
        self.retriever: "Optional[HybridRetriever]" = None
        self.generator: "Optional[RecipeGenerator]" = None
        self.chunks = None

    def build_index(self, force_rebuild: bool = False):
        """Load recipes, embed them, and index into Qdrant.

        Incremental by default: every chunk gets a stable point_id (derived from its
        (source_file, chunk_id) composite key — see _point_id()) and a per-chunk
        content hash, both tracked in an on-disk manifest. Each run diffs the freshly
        loaded chunks against that manifest and only embeds+upserts what's new or
        changed, deletes what's been removed from the source, and leaves everything
        else untouched — so adding a handful of new recipes stays cheap no matter how
        large the existing corpus already is.

        force_rebuild=True always fully wipes the collection and re-embeds
        everything regardless of any diffing — the escape hatch for a real
        embedding-model change (e.g. MiniLM -> bge-base), where every existing
        vector is stale by definition and diffing against it would be wrong.

        Separately, an old-format manifest (pre-dating per-chunk point IDs) or a
        missing/unparseable one is NOT diffed against — it can't be, it doesn't have
        the per-chunk data — so it triggers exactly one full rebuild to migrate to
        the new format, the same as force_rebuild=True, after which every later call
        goes through the incremental path above.
        """
        from .embedder import TextEmbedder
        from .hybrid_retriever import HybridRetriever
        from .recipe_loader import load_recipe_sources, print_recipe_statistics
        from .reranker import CrossEncoderReranker
        from .vector_database import QdrantVectorDB

        logger.info("Building recipe index...")
        start = time.time()

        self.embedder = TextEmbedder(self.config.EMBEDDING_MODEL)
        self.config.EMBEDDING_DIMENSION = self.embedder.dimension

        self.vector_db = QdrantVectorDB(self.config)
        existing_count = self.vector_db.count_documents()

        self.chunks = load_recipe_sources(self.config.RECIPE_SOURCES)
        print_recipe_statistics(self.chunks)

        manifest_path = Path(self.config.VECTOR_DB_PATH) / f"{self.config.VECTOR_DB_COLLECTION}.manifest.json"
        manifest = None
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not read index manifest, will rebuild: {e}")

        chunk_ids = [_point_id(c["source_file"], c["chunk_id"]) for c in self.chunks]
        current_map = {
            pid: _chunk_hash(chunk, self.config.EMBEDDING_MODEL)
            for pid, chunk in zip(chunk_ids, self.chunks)
        }

        # A manifest is only usable for diffing if it's in the new per-chunk format
        # for the embedding model we're about to use. An empty collection paired
        # with a manifest that claims non-empty content is also untrustworthy —
        # something wiped Qdrant out from under the manifest, so don't diff against
        # stale bookkeeping that no longer matches reality.
        stored_map = manifest.get("chunks") if manifest else None
        is_new_format = (
            stored_map is not None
            and manifest.get("embedding_model") == self.config.EMBEDDING_MODEL
            and (existing_count > 0 or not stored_map)
        )

        if force_rebuild or not is_new_format:
            if not force_rebuild:
                if manifest is None:
                    logger.info("No existing manifest found — building index from scratch.")
                else:
                    logger.info(
                        "Old manifest format detected, doing one full rebuild to migrate to stable point IDs."
                    )
            logger.info(f"(Re)building index — {existing_count} indexed vs {len(self.chunks)} loaded recipes.")
            self.vector_db.create_collection(force_recreate=True)

            texts = [c["text"] for c in self.chunks]
            embeddings = self.embedder.embed_texts(texts)
            docs = [
                _doc_from_chunk(chunk, pid, embeddings[i])
                for i, (chunk, pid) in enumerate(zip(self.chunks, chunk_ids))
            ]
            self.vector_db.index_documents(docs)
            _write_manifest(manifest_path, self.config.EMBEDDING_MODEL, current_map)
        else:
            new_or_changed_ids = [pid for pid, h in current_map.items() if stored_map.get(pid) != h]
            removed_ids = [pid for pid in stored_map if pid not in current_map]

            if not new_or_changed_ids and not removed_ids:
                logger.info(
                    f"Index already up to date ({existing_count} recipes, no new/changed/removed "
                    "chunks). Skipping re-embedding."
                )
            else:
                if new_or_changed_ids:
                    chunk_by_id = dict(zip(chunk_ids, self.chunks))
                    changed_chunks = [chunk_by_id[pid] for pid in new_or_changed_ids]
                    embeddings = self.embedder.embed_texts([c["text"] for c in changed_chunks])
                    docs = [
                        _doc_from_chunk(chunk, pid, embeddings[i])
                        for i, (chunk, pid) in enumerate(zip(changed_chunks, new_or_changed_ids))
                    ]
                    self.vector_db.index_documents(docs)
                    logger.info(f"Embedded and upserted {len(docs)} new/changed chunk(s).")

                if removed_ids:
                    self.vector_db.delete_points(removed_ids)
                    logger.info(f"Deleted {len(removed_ids)} chunk(s) removed from the source.")

                _write_manifest(manifest_path, self.config.EMBEDDING_MODEL, current_map)

        if self.config.USE_HYBRID_RETRIEVAL:
            reranker = CrossEncoderReranker(self.config.RERANKER_MODEL) if self.config.USE_RERANKER else None
            self.retriever = HybridRetriever(
                chunks=self.chunks, embedder=self.embedder, vector_db=self.vector_db,
                top_k=self.config.TOP_K, reranker=reranker,
            )

        logger.info(f"Index ready in {time.time() - start:.1f}s")

    def build_index_remote(self, rag_service_url: str):
        """Used by pipeline_server.py in the split-service deployment: skips loading the
        embedder/vector_db/BM25 index locally (that's the retrieval service's job) and
        just points self.retrieve() at it over HTTP instead. Keeps run_query()/
        run_query_stream()/filter_grounded() unchanged since they only depend on
        self.retriever.retrieve() having the same return shape as HybridRetriever's."""
        from .retrieval_client import RemoteRetriever
        self.retriever = RemoteRetriever(rag_service_url)

    def initialize_generator(self):
        from .generator import RecipeGenerator

        self.generator = RecipeGenerator(
            base_url=self.config.OLLAMA_BASE_URL,
            model=self.config.LLM_MODEL,
            api_key=self.config.OLLAMA_API_KEY,
            api_style=self.config.LLM_API_STYLE,
            temperature=self.config.LLM_TEMPERATURE,
            top_p=self.config.LLM_TOP_P,
            max_tokens=self.config.LLM_MAX_TOKENS,
            max_retries=self.config.LLM_MAX_RETRIES,
            retry_delay=self.config.LLM_RETRY_DELAY,
        )

    def retrieve(self, question: str, top_k: int = None):
        top_k = top_k or self.config.TOP_K
        if self.retriever is not None:
            return self.retriever.retrieve(question, top_k=top_k)

        query_emb = self.embedder.embed_query(question)
        return self.vector_db.retrieve(query_emb, top_k=top_k)

    def filter_grounded(self, retrieved: list) -> list:
        """The relevance gate shared by run_query() and run_eval.py — kept as one method
        instead of copy-pasted logic so the two can't silently drift out of sync (as they
        briefly did while wiring in the reranker). rerank_score (cross-encoder) is a much
        cleaner relevance signal than dense similarity when the reranker is enabled — see
        reranker.py and config.py for the empirical comparison. Falls back to dense/RRF
        score if reranking is off."""
        if self.config.USE_RERANKER:
            return [r for r in retrieved if r.get("rerank_score", -1e9) >= self.config.MIN_RERANK_SCORE]
        return [r for r in retrieved if r.get("dense_score", r.get("score", 0)) >= self.config.MIN_DENSE_SCORE]

    def find_recipes_from_ingredients(
        self, ingredients: list, max_results: int = 10, normalize: bool = False,
    ) -> list:
        """Retrieval-only recipe discovery: given a set of ingredients, return up to
        max_results matching corpus recipes, no LLM call involved. Distinct from
        run_query()/run_query_stream(), which always synthesize one merged answer — this
        is for "what could I cook with X, Y, Z" browsing where several real candidates
        are more useful than one generated recipe. Foundation for the discount-driven
        recipe flow (v2): feed it currently-discounted ingredients, get back real corpus
        recipes that use them, with no per-candidate generation cost.

        Retrieves a wider pool than max_results before filtering, since naively
        retrieving exactly max_results and THEN filtering could return fewer than
        max_results even when more genuine matches exist further down the ranking.

        normalize=True runs each ingredient through normalize_grocery_heading() before
        building the retrieval query -- raw Norwegian grocery-flyer headings (e.g.
        "REKER I LØSVEKT") score catastrophically low against this app's English-only
        corpus/reranker (confirmed live: best rerank score -9.18, 0/15 pass vs. +5.77,
        15/15 pass for the translated "shrimp"), so real corpus matches get wrongly
        rejected by filter_grounded() without it. Defaults to False and must NOT be
        applied unconditionally: an adversarial review confirmed normalize_grocery_heading()
        corrupts plain English free text a real user could type (e.g. "extra virgin olive
        oil" -> "virgin olive oil", "clam chowder with bacon" -> "lamb chowder with
        bacon") via glossary/noise-token suffix collisions that were only ever validated
        against real Norwegian Tjek headings, not English vocabulary. Callers must only
        pass normalize=True when the ingredients are structurally known to come from Tjek
        (see /recipes/discounted in pipeline_server.py), never for arbitrary user input."""
        from .grocery_terms import normalize_grocery_heading
        if normalize:
            query = ", ".join(normalize_grocery_heading(ing) for ing in ingredients)
        else:
            query = ", ".join(ingredients)
        retrieved = self.retrieve(query, top_k=max(max_results * 3, 15))
        grounded = self.filter_grounded(retrieved)
        return grounded[:max_results]

    def find_recipes_or_generate(
        self, ingredients: list, max_results: int = 10, normalize: bool = False,
    ) -> Dict[str, Any]:
        """Wraps find_recipes_from_ingredients() with an LLM fallback for when nothing in
        the corpus matches — e.g. an obscure dish/cuisine combination the corpus doesn't
        cover. Returns real corpus recipes when available; several clearly-labeled
        generated suggestions when not (never just one — the whole point of this endpoint
        is offering options, so the fallback should too), rather than leaving the caller
        empty-handed. Both branches return "recipes" in the same {title, text,
        rerank_score, dense_score} shape so callers don't need branch-specific handling;
        rerank_score/dense_score are None for generated entries since they're not
        corpus-verified. "source" lets a caller distinguish a verified corpus match from
        a generated-and-possibly-hallucinated one, same as run_query()'s grounded field.

        normalize is forwarded to find_recipes_from_ingredients() and to the generation
        prompt below -- see that method's docstring for why this defaults to False and
        must only be set True for structurally-known-Tjek input."""
        grounded = self.find_recipes_from_ingredients(
            ingredients, max_results=max_results, normalize=normalize,
        )
        if grounded:
            recipes = [
                {
                    "title": r["payload"].get("title"),
                    "text": r["text"],
                    "rerank_score": r.get("rerank_score"),
                    "dense_score": r.get("dense_score"),
                }
                for r in grounded
            ]
            return {"source": "corpus", "recipes": recipes, "generated": None, "error": None}

        # Asking for N recipes in one completion doesn't work — confirmed empirically:
        # the fine-tuned model always produces exactly one recipe regardless of the
        # instruction, almost certainly because it was fine-tuned on single-question ->
        # single-recipe pairs, not because of anything in the system prompt (this
        # pipeline's own SYSTEM_PROMPT already replaces whatever's in the Modelfile for
        # these calls, and the behavior persists anyway). Making N separate calls works
        # WITH that trained-in habit instead of fighting it.
        #
        # Getting those N calls to actually diverge took two layers, found by tracing the
        # Modelfile (recipe-model/v3/Modelfile has "PARAMETER temperature 0.1" baked in
        # at build time): (1) options={"temperature": 0.9} alone did nothing when tested
        # through OpenWebUI/chat.bebs.dev — 3 identical calls returned byte-identical
        # output, meaning OpenWebUI silently ignores/pins the client-requested
        # temperature for this model. Confirmed via a direct curl to native Ollama
        # (bypassing OpenWebUI) that the SAME override produces genuinely different
        # output there — and pipeline_server.py already talks to native Ollama in
        # production (LLM_API_STYLE=ollama, host.docker.internal:11434), so this override
        # works in the deployment that matters even though it looked broken in local dev
        # (which defaults to the OpenWebUI route). (2) Varying prompt CONTENT (not just
        # phrasing) on top of that gives a second, deployment-independent source of
        # diversity, so this doesn't silently regress to 1 recipe again if the
        # OpenWebUI-vs-Ollama routing ever changes. Capped at 3 fixed angles — more calls
        # means more latency on what's already the slow fallback path.
        angles = [
            "What can I cook with these ingredients: {ing}?",
            "Give me a soup, stew, or braised dish I could make with these ingredients: {ing}.",
            "Give me a quick, simple recipe using these ingredients: {ing}.",
        ]

        # Same normalize flag as find_recipes_from_ingredients() above, applied here too
        # so the generation prompt doesn't hit the same raw-Norwegian-text hallucination
        # problem retrieval does (confirmed live: raw 'REKER I LØSVEKT' fed straight to
        # the LLM produced an egg-fritter recipe, a beef-short-rib recipe, and a
        # mackerel pie -- none related to shrimp) when normalize=True. When normalize is
        # False (the default -- arbitrary user-typed free text), skip
        # normalize_grocery_heading() entirely: it corrupts real English ingredient
        # phrases (see find_recipes_from_ingredients()'s docstring for confirmed
        # examples), so it must never run on this path. ingredients itself (the caller's
        # original list) is left untouched here either way -- only this local
        # normalized_ingredients is used for the prompt.
        if normalize:
            from .grocery_terms import normalize_grocery_heading
            normalized_ingredients = ", ".join(normalize_grocery_heading(ing) for ing in ingredients)
        else:
            normalized_ingredients = ", ".join(ingredients)

        n = min(max_results, len(angles))
        recipes, answers, errors = [], [], []
        for i in range(n):
            question = angles[i].format(ing=normalized_ingredients)
            try:
                answer = self.generator.generate(
                    question, "(no matching reference recipe found)", SYSTEM_PROMPT,
                    options={"temperature": 0.9},
                )
                answers.append(answer)
                parsed = _split_generated_recipes(answer)
                # Fall back to treating the whole answer as one recipe if the model
                # didn't use the "### Title" heading this call — still usable content,
                # just without a clean parsed title.
                if parsed:
                    recipes.extend(parsed)
                else:
                    recipes.append({"title": None, "text": answer})
            except Exception as e:
                logger.error(f"Fallback generation {i + 1}/{n} failed for ingredients {ingredients!r}: {e}")
                errors.append(str(e))

        recipes = [
            {"title": r["title"], "text": r["text"], "rerank_score": None, "dense_score": None}
            for r in recipes
        ]
        return {
            "source": "generated",
            "recipes": recipes,
            "generated": "\n\n".join(answers) if answers else None,
            "error": "; ".join(errors) if errors and not recipes else None,
        }

    def _retrieve_and_build_context(self, question: str, top_k: int = None):
        """Shared by run_query() and run_query_stream() — retrieval/grounding is identical
        either way, only what happens with the generated answer differs (buffered vs streamed)."""
        retrieved = self.retrieve(question, top_k)
        grounded = self.filter_grounded(retrieved)
        context = "\n\n".join(
            f"[Reference {i+1}: {r['payload'].get('title', 'unknown')}]\n{r['text']}"
            for i, r in enumerate(grounded)
        ) or "(no matching reference recipe found)"
        return retrieved, grounded, context

    def run_query(self, question: str, top_k: int = None) -> Dict[str, Any]:
        start = time.time()
        retrieved, grounded, context = self._retrieve_and_build_context(question, top_k)

        # answer is None on failure, never an error string masquerading as a recipe —
        # callers must check `error` before displaying `answer`.
        answer, error = None, None
        try:
            answer = self.generator.generate(question, context, SYSTEM_PROMPT)
        except Exception as e:
            logger.error(f"Generation failed for {question!r}: {e}")
            error = str(e)

        return {
            "question": question,
            "retrieved": retrieved,
            "grounded": grounded,
            "context": context,
            "answer": answer,
            "error": error,
            "elapsed": time.time() - start,
        }

    def run_query_stream(self, question: str, top_k: int = None) -> Iterator[Dict[str, Any]]:
        """Streaming counterpart to run_query() — yields a tagged sequence a caller can
        react to progressively instead of waiting 15-40s for the full answer:
          {"type": "meta", "retrieved": [...], "grounded": [...]}   (once, first)
          {"type": "chunk", "text": "..."}                          (many, as tokens arrive)
          {"type": "error", "error": "..."}                         (only on failure, last)
        """
        start = time.time()
        retrieved, grounded, context = self._retrieve_and_build_context(question, top_k)
        yield {"type": "meta", "retrieved": retrieved, "grounded": grounded}

        try:
            for chunk in self.generator.generate_stream(question, context, SYSTEM_PROMPT):
                yield {"type": "chunk", "text": chunk}
        except Exception as e:
            logger.error(f"Generation failed for {question!r}: {e}")
            yield {"type": "error", "error": str(e)}

        yield {"type": "done", "elapsed": time.time() - start}

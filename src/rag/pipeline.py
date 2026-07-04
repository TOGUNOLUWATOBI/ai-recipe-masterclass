"""Recipe RAG pipeline: retrieve a matching curated recipe (if one exists) and ground
the fine-tuned model's answer in it, instead of relying purely on what got baked into
the model's weights during training.
"""

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

from .config import RecipeRAGConfig

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


def _content_hash(chunks, embedding_model: str) -> str:
    """Hash of actual recipe content + embedding model, not just a row count — a count-only
    check would silently keep serving stale embeddings if a recipe's text changed without
    changing the total number of recipes, or if the embedding model changed (as it did when
    we switched MiniLM -> bge-base and had to remember to pass force_rebuild manually)."""
    hasher = hashlib.sha256()
    hasher.update(embedding_model.encode("utf-8"))
    for chunk in sorted(chunks, key=lambda c: (c["source_file"], c["chunk_id"])):
        hasher.update(chunk["text"].encode("utf-8"))
    return hasher.hexdigest()


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
        """Load recipes, embed them, and index into Qdrant. Skips re-embedding if the
        collection already has documents and force_rebuild is False."""
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
        current_hash = _content_hash(self.chunks, self.config.EMBEDDING_MODEL)
        stored_hash = None
        if manifest_path.exists():
            try:
                stored_hash = json.loads(manifest_path.read_text()).get("content_hash")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not read index manifest, will rebuild: {e}")

        up_to_date = existing_count > 0 and stored_hash == current_hash
        if not force_rebuild and up_to_date:
            logger.info(f"Index already up to date ({existing_count} recipes, content unchanged). Skipping re-embedding.")
        else:
            logger.info(f"(Re)building index — {existing_count} indexed vs {len(self.chunks)} loaded recipes.")
            self.vector_db.create_collection(force_recreate=True)

            texts = [c["text"] for c in self.chunks]
            embeddings = self.embedder.embed_texts(texts)

            docs = [
                {
                    "id": i,
                    "embedding": embeddings[i],
                    "text": chunk["text"],
                    "metadata": {
                        "title": chunk["title"],
                        "source_file": chunk["source_file"],
                        "chunk_id": chunk["chunk_id"],
                    },
                }
                for i, chunk in enumerate(self.chunks)
            ]
            self.vector_db.index_documents(docs)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps({
                "content_hash": current_hash,
                "embedding_model": self.config.EMBEDDING_MODEL,
                "recipe_count": len(self.chunks),
            }))

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

    def find_recipes_from_ingredients(self, ingredients: list, max_results: int = 10) -> list:
        """Retrieval-only recipe discovery: given a set of ingredients, return up to
        max_results matching corpus recipes, no LLM call involved. Distinct from
        run_query()/run_query_stream(), which always synthesize one merged answer — this
        is for "what could I cook with X, Y, Z" browsing where several real candidates
        are more useful than one generated recipe. Foundation for the discount-driven
        recipe flow (v2): feed it currently-discounted ingredients, get back real corpus
        recipes that use them, with no per-candidate generation cost.

        Retrieves a wider pool than max_results before filtering, since naively
        retrieving exactly max_results and THEN filtering could return fewer than
        max_results even when more genuine matches exist further down the ranking."""
        query = ", ".join(ingredients)
        retrieved = self.retrieve(query, top_k=max(max_results * 3, 15))
        grounded = self.filter_grounded(retrieved)
        return grounded[:max_results]

    def find_recipes_or_generate(self, ingredients: list, max_results: int = 10) -> Dict[str, Any]:
        """Wraps find_recipes_from_ingredients() with an LLM fallback for when nothing in
        the corpus matches — e.g. an obscure dish/cuisine combination the corpus doesn't
        cover. Returns real corpus recipes when available; several clearly-labeled
        generated suggestions when not (never just one — the whole point of this endpoint
        is offering options, so the fallback should too), rather than leaving the caller
        empty-handed. Both branches return "recipes" in the same {title, text,
        rerank_score, dense_score} shape so callers don't need branch-specific handling;
        rerank_score/dense_score are None for generated entries since they're not
        corpus-verified. "source" lets a caller distinguish a verified corpus match from
        a generated-and-possibly-hallucinated one, same as run_query()'s grounded field."""
        grounded = self.find_recipes_from_ingredients(ingredients, max_results=max_results)
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
        n = min(max_results, len(angles))
        recipes, answers, errors = [], [], []
        for i in range(n):
            question = angles[i].format(ing=", ".join(ingredients))
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

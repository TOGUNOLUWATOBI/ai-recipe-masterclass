"""Cross-encoder reranking — a second-stage relevance judge over the small candidate set
a bi-encoder + BM25 already narrowed down, not a replacement for them.

Bi-encoders (embedder.py) score query and document independently then compare vectors,
which is fast enough to search a whole corpus but is a blunter instrument: it conflates
"shares vocabulary" with "is the same dish" (that's the moi-moi/briyani/ribbe overlap we
found empirically — true and false positives landed in the same 0.50-0.65 cosine-similarity
band). A cross-encoder scores the (query, document) pair jointly, which is far more
precise — confirmed empirically: true matches scored +5 to +8.5, clear false positives
scored -4 to -11, a clean gap with no overlap. It's too slow to run over the whole corpus
(one forward pass per candidate, not a cached vector), which is why it only reranks the
top candidates that hybrid retrieval already surfaced.
"""

import logging
from typing import Any, Dict, List

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        logger.info(f"Loading reranker: {model_name}")
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reranks against title + ingredients (not the full instructions block).

        Originally title-only, which worked well for dish-name queries ("jollof rice")
        but empirically failed ingredient-based ones ("I have eggs, flour, and sugar,
        what can I bake") — a title alone rarely mentions specific ingredients, so the
        cross-encoder had nothing to match an ingredient list against and scored every
        candidate as irrelevant (confirmed: -7.19 title-only vs +1.52 with ingredients
        included, for the exact query that was failing). Instructions are excluded to
        keep the pair short — recipe_loader's text format puts them last, so slicing
        before "**Instructions:**" cheaply gets title+ingredients from the text already
        computed, no need to reconstruct it from payload metadata."""
        if not candidates:
            return candidates

        def title_and_ingredients(candidate: Dict[str, Any]) -> str:
            text = candidate.get("text", "")
            return text.split("**Instructions:**")[0]

        pairs = [(query, title_and_ingredients(c)) for c in candidates]
        scores = self.model.predict(pairs)

        reranked = [{**c, "rerank_score": float(score)} for c, score in zip(candidates, scores)]
        reranked.sort(key=lambda c: c["rerank_score"], reverse=True)
        return reranked

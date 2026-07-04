"""Hybrid retrieval: BM25 (keyword) + dense (semantic) with Reciprocal Rank Fusion.

Adapted from the DAT560 project's HybridRetriever. Dropped the adjacent-chunk context
expansion feature — it doesn't apply here since each recipe is already a single,
self-contained chunk with nothing to expand into.

BM25 matters a lot for this domain specifically: it catches exact dish-name matches
("ribbe", "jollof") even when the dense embedder doesn't have a strong sense of an
unfamiliar dish name, while dense retrieval catches semantic/ingredient-based queries
("what can I make with chicken and rice").
"""

import logging
import re
from typing import Any, Dict, List

import numpy as np
from rank_bm25 import BM25Okapi

from .query_normalizer import build_vocabulary, normalize_query

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


class HybridRetriever:
    RRF_K = 60  # RRF constant — controls rank smoothing
    RERANK_POOL_SIZE = 15  # candidates handed to the reranker before truncating to top_k —
    # wide enough that the reranker can promote something RRF under-ranked, not just
    # re-sort the same handful of results RRF already committed to.

    def __init__(self, chunks: List[Dict[str, Any]], embedder, vector_db, top_k: int = 3, reranker=None):
        self.chunks = chunks
        self.embedder = embedder
        self.vector_db = vector_db
        self.top_k = top_k
        self.reranker = reranker

        logger.info(f"Building BM25 index over {len(chunks)} recipes...")
        tokenized = [_tokenize(chunk["text"]) for chunk in chunks]
        self.bm25 = BM25Okapi(tokenized)
        logger.info("BM25 index built.")

        self.vocabulary = build_vocabulary(chunk["title"] for chunk in chunks)

    def retrieve(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        k = top_k or self.top_k
        pool_size = max(k, self.RERANK_POOL_SIZE) if self.reranker else k
        n_candidates = min(pool_size * 20, len(self.chunks))

        normalized = normalize_query(query, self.vocabulary)
        if normalized != query:
            logger.info(f"Query normalized: {query!r} -> {normalized!r}")
        query = normalized

        # --- Dense retrieval ---
        query_emb = self.embedder.embed_query(query)
        dense_results = self.vector_db.retrieve(query_emb, top_k=n_candidates)
        dense_rank = {r["id"]: rank for rank, r in enumerate(dense_results)}

        # --- BM25 retrieval ---
        bm25_scores = self.bm25.get_scores(_tokenize(query))
        bm25_top_ids = np.argsort(bm25_scores)[::-1][:n_candidates].tolist()
        bm25_rank = {int(idx): rank for rank, idx in enumerate(bm25_top_ids)}

        # --- Reciprocal Rank Fusion ---
        all_ids = set(dense_rank.keys()) | set(bm25_rank.keys())
        rrf_scores = {}
        for doc_id in all_ids:
            dr = dense_rank.get(doc_id, n_candidates)
            br = bm25_rank.get(doc_id, n_candidates)
            rrf_scores[doc_id] = 1 / (self.RRF_K + dr) + 1 / (self.RRF_K + br)

        top_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:pool_size]

        dense_by_id = {r["id"]: r for r in dense_results}
        results = []
        for doc_id in top_ids:
            if doc_id in dense_by_id:
                entry = {
                    **dense_by_id[doc_id],
                    "score": rrf_scores[doc_id],
                    "dense_score": dense_by_id[doc_id]["score"],
                }
            else:
                chunk = self.chunks[doc_id]
                entry = {
                    "id": doc_id,
                    "score": rrf_scores[doc_id],
                    "dense_score": 0.0,  # BM25-only hit
                    "text": chunk["text"],
                    "payload": {
                        "title": chunk["title"],
                        "source_file": chunk["source_file"],
                        "chunk_id": chunk["chunk_id"],
                    },
                }
            results.append(entry)

        if self.reranker:
            results = self.reranker.rerank(query, results)[:k]

        return results

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

        # Dense retrieval identifies a chunk by its Qdrant point id (a uuid5 of
        # source_file+chunk_id, see pipeline._point_id()); BM25 identifies the same
        # chunk by its plain position in `chunks` (np.argsort() below returns array
        # indices). Those are two different id spaces for the same underlying chunk --
        # without translating one into the other before RRF fusion, a chunk retrieved
        # by BOTH methods gets counted as two separate candidates (one dense hit under
        # its Qdrant uuid, one BM25 hit under its chunks-index) instead of being merged
        # into one, and the exact same recipe surfaces twice in the results (confirmed
        # live: searching "sirloin" returned each of the top 3 corpus recipes twice,
        # back to back). This map lets retrieve() re-key every dense hit to its
        # chunks-index, the same id space BM25 already uses, so the two can actually be
        # deduplicated. A deferred import -- pipeline.py only ever constructs this class
        # lazily inside build_index() specifically so pipeline-service's container,
        # which never calls build_index() and doesn't have rank_bm25/torch installed,
        # never has to import this module at all; importing pipeline.py back from here
        # at module load time would defeat that.
        from .pipeline import _point_id
        self._point_id_to_index = {
            _point_id(chunk["source_file"], chunk["chunk_id"]): i for i, chunk in enumerate(chunks)
        }

    def retrieve(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        k = top_k or self.top_k
        pool_size = max(k, self.RERANK_POOL_SIZE) if self.reranker else k
        n_candidates = min(pool_size * 20, len(self.chunks))

        normalized = normalize_query(query, self.vocabulary)
        if normalized != query:
            logger.info(f"Query normalized: {query!r} -> {normalized!r}")
        query = normalized

        # --- Dense retrieval ---
        # Re-keyed from Qdrant's own point id to this chunk's position in `self.chunks`
        # (see the id-space comment in __init__) -- the same id space bm25_rank below
        # uses, so a chunk hit by both methods fuses into one candidate instead of two.
        # A Qdrant point with no matching in-memory chunk (a stale index entry) is
        # skipped rather than crashing -- it can't be deduplicated against anyway.
        query_emb = self.embedder.embed_query(query)
        dense_results = self.vector_db.retrieve(query_emb, top_k=n_candidates)
        dense_rank = {}
        dense_by_index = {}
        for rank, r in enumerate(dense_results):
            idx = self._point_id_to_index.get(r["id"])
            if idx is None:
                continue
            dense_rank[idx] = rank
            dense_by_index[idx] = r

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

        results = []
        for doc_id in top_ids:
            if doc_id in dense_by_index:
                r = dense_by_index[doc_id]
                entry = {
                    **r,
                    "score": rrf_scores[doc_id],
                    "dense_score": r["score"],
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

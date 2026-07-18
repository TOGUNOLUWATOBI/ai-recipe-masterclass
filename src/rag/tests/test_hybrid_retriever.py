"""Tests for hybrid_retriever.py's dense+BM25 Reciprocal Rank Fusion -- specifically
the id-space bug where a chunk retrieved by both methods used to count as two separate
candidates: dense results are keyed by a Qdrant point id (uuid5 of source_file+chunk_id,
see pipeline._point_id()) while BM25 results are keyed by a plain position in the chunks
list, and RRF fusion never translated one into the other before this fix. Confirmed
live in production: searching "sirloin" against the real corpus returned each of the
top 3 corpus recipes twice, back to back (recipe 1 == recipe 2, 3 == 4, 5 == 6) --
exactly this bug, since "sirloin" scored well by both dense and BM25 for the same
handful of real recipes.

Needs numpy/rank_bm25 (this module's own real dependencies) -- run inside an
environment with requirements-retrieval.txt installed (e.g. the rag-service
container), not necessarily this repo's default local dev environment."""

from rag.hybrid_retriever import HybridRetriever
from rag.pipeline import _point_id


def _chunk(text, source="a.json", chunk_id=0, title="Test"):
    return {"text": text, "source_file": source, "chunk_id": chunk_id, "title": title}


class _FakeEmbedder:
    def embed_query(self, query):
        return [0.0]  # value is irrelevant -- _FakeVectorDB.retrieve() ignores it


class _FakeVectorDB:
    """Returns exactly the dense hits a test configures, already keyed by the real
    Qdrant point id (_point_id) so the fix under test is exercised faithfully."""

    def __init__(self, hits):
        self.hits = hits

    def retrieve(self, query_emb, top_k):
        return self.hits[:top_k]


def test_a_chunk_retrieved_by_both_dense_and_bm25_is_returned_exactly_once():
    """The core regression: before the fix, this chunk's Qdrant point id (dense) and
    its chunks-list position (BM25) were treated as two different RRF candidates, so
    it survived into the final results twice."""
    chunks = [
        _chunk("chicken curry rice spicy", source="a.json", chunk_id=0, title="Chicken Curry"),
        _chunk("something else entirely about salad", source="b.json", chunk_id=1, title="Salad"),
    ]
    dense_hit = {
        "id": _point_id("a.json", 0), "score": 0.9,
        "text": chunks[0]["text"],
        "payload": {"title": chunks[0]["title"], "source_file": "a.json", "chunk_id": 0},
    }
    retriever = HybridRetriever(chunks, embedder=_FakeEmbedder(), vector_db=_FakeVectorDB([dense_hit]), top_k=5)

    results = retriever.retrieve("chicken curry")

    matches = [r for r in results if r["payload"]["chunk_id"] == 0]
    assert len(matches) == 1
    # The surviving entry must be the fused one (real dense_score), not an arbitrary
    # pick between the dense hit and the BM25-only fallback -- confirms the fix
    # actually merges the two candidates rather than just discarding one at random.
    assert matches[0]["dense_score"] == 0.9


def test_a_bm25_only_hit_still_reports_a_dense_score_of_zero():
    """Unrelated to the dedup fix -- a chunk with no dense hit at all (e.g. an unusual
    dish name the embedder doesn't recognize well) must still surface via the
    BM25-only fallback branch, same as before the fix."""
    chunks = [_chunk("obscure regional stew keyword", source="a.json", chunk_id=0, title="Obscure Stew")]
    retriever = HybridRetriever(chunks, embedder=_FakeEmbedder(), vector_db=_FakeVectorDB([]), top_k=5)

    results = retriever.retrieve("obscure regional stew")

    assert len(results) == 1
    assert results[0]["dense_score"] == 0.0
    assert results[0]["payload"]["title"] == "Obscure Stew"


def test_a_dense_hit_with_no_matching_in_memory_chunk_is_skipped_not_crashed():
    """A stale Qdrant point (from a corpus that's since shrunk/changed) has no
    corresponding entry in this retriever's in-memory chunks list -- must be silently
    skipped, not a KeyError, since build_index()'s own incremental diffing (not this
    class) is what's responsible for keeping Qdrant in sync in the first place."""
    chunks = [_chunk("chicken curry rice", source="a.json", chunk_id=0, title="Chicken Curry")]
    stale_hit = {
        "id": _point_id("removed.json", 99), "score": 0.9,
        "text": "some removed recipe",
        "payload": {"title": "Removed", "source_file": "removed.json", "chunk_id": 99},
    }
    retriever = HybridRetriever(chunks, embedder=_FakeEmbedder(), vector_db=_FakeVectorDB([stale_hit]), top_k=5)

    results = retriever.retrieve("chicken curry")

    assert all(r["payload"]["title"] != "Removed" for r in results)

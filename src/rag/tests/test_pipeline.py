"""Tests for pipeline.py's pure logic — _point_id, _chunk_hash, build_index's
incremental-indexing diff logic, and filter_grounded — without touching the real
embedder/Qdrant/generator (those need models and a live corpus)."""

import json

from rag.config import RecipeRAGConfig
from rag.pipeline import (
    RecipeRAGPipeline,
    _chunk_hash,
    _point_id,
    _split_generated_recipes,
)


def _chunk(text, source="a.json", chunk_id=0, title="Test"):
    return {"text": text, "source_file": source, "chunk_id": chunk_id, "title": title}


def test_point_id_is_deterministic():
    """Same (source_file, chunk_id) must produce the same UUID across two separate
    calls — this is what makes incremental indexing possible at all: without a
    stable id, there'd be no way to recognize "the same chunk as last time" once the
    corpus has grown, shrunk, or reordered around it."""
    assert _point_id("a.json", 3) == _point_id("a.json", 3)


def test_point_id_differs_for_different_chunks():
    assert _point_id("a.json", 0) != _point_id("a.json", 1)
    assert _point_id("a.json", 0) != _point_id("b.json", 0)


def test_chunk_hash_is_deterministic():
    chunk = _chunk("### Jollof Rice\n\nA")
    assert _chunk_hash(chunk, "model-x") == _chunk_hash(chunk, "model-x")


def test_chunk_hash_changes_when_text_changes():
    original = _chunk("### Jollof Rice\n\nOriginal ingredients")
    edited = _chunk("### Jollof Rice\n\nCompletely different ingredients")
    assert _chunk_hash(original, "model-x") != _chunk_hash(edited, "model-x")


def test_chunk_hash_changes_when_embedding_model_changes():
    """Regression test: switching MiniLM -> bge-base needed a manual force_rebuild the
    first time, because the old whole-corpus check didn't know the embedding model
    itself had changed. Same principle applies per-chunk now."""
    chunk = _chunk("### Jollof Rice\n\nA")
    assert _chunk_hash(chunk, "minilm") != _chunk_hash(chunk, "bge-base")


def test_chunk_hash_is_independent_of_other_chunks():
    """Unlike the old whole-corpus _content_hash, a per-chunk hash must depend only on
    that chunk's own text — not on what else happens to be loaded alongside it."""
    a = _chunk("### A\n\nfoo", chunk_id=0)
    assert _chunk_hash(a, "model-x") == _chunk_hash(dict(a), "model-x")


# ---------------------------------------------------------------------------
# build_index() incremental-indexing behavior. Fakes for the embedder/vector_db/
# recipe loader so these tests don't need a real model or Qdrant instance —
# build_index() imports TextEmbedder/QdrantVectorDB/load_recipe_sources/etc. lazily
# from their own modules, so patching the class/function on those modules (rather
# than on rag.pipeline) is what actually takes effect.
# ---------------------------------------------------------------------------


class _FakeEmbedder:
    def __init__(self, model_name):
        self.dimension = 8
        self.calls = []

    def embed_texts(self, texts, batch_size=64):
        self.calls.append(list(texts))
        return [[0.0] * self.dimension for _ in texts]


class _FakeVectorDB:
    def __init__(self, config):
        self.config = config
        self.created = []
        self.indexed_docs = []
        self.deleted_ids = []
        self._count = 0

    def create_collection(self, force_recreate=False):
        self.created.append(force_recreate)

    def index_documents(self, documents, batch_size=100):
        self.indexed_docs.append(documents)
        return len(documents)

    def delete_points(self, ids):
        self.deleted_ids.append(list(ids))

    def count_documents(self):
        return self._count


def _make_pipeline(tmp_path, chunks, embedding_model="bge-base", hybrid=False):
    config = RecipeRAGConfig(
        VECTOR_DB_PATH=str(tmp_path),
        VECTOR_DB_COLLECTION="recipes",
        EMBEDDING_MODEL=embedding_model,
        USE_HYBRID_RETRIEVAL=hybrid,
    )
    pipeline = RecipeRAGPipeline(config)
    return pipeline, chunks


def test_build_index_old_format_manifest_triggers_one_full_rebuild_and_migrates(tmp_path, monkeypatch):
    manifest_path = tmp_path / "recipes.manifest.json"
    manifest_path.write_text(json.dumps({
        "content_hash": "deadbeef",
        "embedding_model": "bge-base",
        "recipe_count": 1,
    }))

    chunks = [_chunk("### Jollof Rice\n\nA")]
    fake_embedder = _FakeEmbedder("bge-base")
    fake_db = _FakeVectorDB(RecipeRAGConfig())
    fake_db._count = 1

    import rag.embedder
    import rag.recipe_loader
    import rag.vector_database
    monkeypatch.setattr(rag.embedder, "TextEmbedder", lambda model_name: fake_embedder)
    monkeypatch.setattr(rag.recipe_loader, "load_recipe_sources", lambda paths: chunks)
    monkeypatch.setattr(rag.recipe_loader, "print_recipe_statistics", lambda chunks: None)
    monkeypatch.setattr(rag.vector_database, "QdrantVectorDB", lambda config: fake_db)

    pipeline, _ = _make_pipeline(tmp_path, chunks)
    pipeline.build_index()

    # Exactly one full rebuild: collection recreated, everything embedded in one call.
    assert fake_db.created == [True]
    assert len(fake_embedder.calls) == 1
    assert len(fake_embedder.calls[0]) == 1
    assert len(fake_db.indexed_docs) == 1
    assert len(fake_db.indexed_docs[0]) == 1

    new_manifest = json.loads(manifest_path.read_text())
    assert "chunks" in new_manifest
    assert new_manifest["embedding_model"] == "bge-base"
    expected_id = _point_id("a.json", 0)
    assert expected_id in new_manifest["chunks"]


def test_build_index_new_format_manifest_with_no_changes_touches_nothing(tmp_path, monkeypatch):
    chunks = [_chunk("### Jollof Rice\n\nA", source="a.json", chunk_id=0)]
    point_id = _point_id("a.json", 0)
    chunk_hash = _chunk_hash(chunks[0], "bge-base")

    manifest_path = tmp_path / "recipes.manifest.json"
    manifest_path.write_text(json.dumps({
        "embedding_model": "bge-base",
        "chunks": {point_id: chunk_hash},
    }))

    fake_embedder = _FakeEmbedder("bge-base")
    fake_db = _FakeVectorDB(RecipeRAGConfig())
    fake_db._count = 1

    import rag.embedder
    import rag.recipe_loader
    import rag.vector_database
    monkeypatch.setattr(rag.embedder, "TextEmbedder", lambda model_name: fake_embedder)
    monkeypatch.setattr(rag.recipe_loader, "load_recipe_sources", lambda paths: chunks)
    monkeypatch.setattr(rag.recipe_loader, "print_recipe_statistics", lambda chunks: None)
    monkeypatch.setattr(rag.vector_database, "QdrantVectorDB", lambda config: fake_db)

    pipeline, _ = _make_pipeline(tmp_path, chunks)
    pipeline.build_index()

    assert fake_db.created == []          # collection never touched
    assert fake_embedder.calls == []      # embedder never called
    assert fake_db.indexed_docs == []     # no upserts
    assert fake_db.deleted_ids == []      # no deletes


def test_build_index_single_new_chunk_causes_exactly_one_embed_and_upsert_call(tmp_path, monkeypatch):
    existing_chunk = _chunk("### Jollof Rice\n\nA", source="a.json", chunk_id=0)
    new_chunk = _chunk("### Egusi Soup\n\nB", source="a.json", chunk_id=1)
    chunks = [existing_chunk, new_chunk]

    existing_id = _point_id("a.json", 0)
    existing_hash = _chunk_hash(existing_chunk, "bge-base")

    manifest_path = tmp_path / "recipes.manifest.json"
    manifest_path.write_text(json.dumps({
        "embedding_model": "bge-base",
        "chunks": {existing_id: existing_hash},
    }))

    fake_embedder = _FakeEmbedder("bge-base")
    fake_db = _FakeVectorDB(RecipeRAGConfig())
    fake_db._count = 1

    import rag.embedder
    import rag.recipe_loader
    import rag.vector_database
    monkeypatch.setattr(rag.embedder, "TextEmbedder", lambda model_name: fake_embedder)
    monkeypatch.setattr(rag.recipe_loader, "load_recipe_sources", lambda paths: chunks)
    monkeypatch.setattr(rag.recipe_loader, "print_recipe_statistics", lambda chunks: None)
    monkeypatch.setattr(rag.vector_database, "QdrantVectorDB", lambda config: fake_db)

    pipeline, _ = _make_pipeline(tmp_path, chunks)
    pipeline.build_index()

    assert fake_db.created == []                  # collection NOT recreated
    assert len(fake_embedder.calls) == 1           # exactly one embed call...
    assert fake_embedder.calls[0] == ["### Egusi Soup\n\nB"]  # ...for only the new chunk
    assert len(fake_db.indexed_docs) == 1          # exactly one upsert call
    assert len(fake_db.indexed_docs[0]) == 1
    assert fake_db.indexed_docs[0][0]["id"] == _point_id("a.json", 1)
    assert fake_db.deleted_ids == []

    new_manifest = json.loads(manifest_path.read_text())["chunks"]
    assert set(new_manifest.keys()) == {existing_id, _point_id("a.json", 1)}


def test_build_index_removed_chunk_triggers_delete_points_with_exactly_its_id(tmp_path, monkeypatch):
    remaining_chunk = _chunk("### Jollof Rice\n\nA", source="a.json", chunk_id=0)
    chunks = [remaining_chunk]  # "### Egusi Soup" chunk_id=1 existed before, gone now

    remaining_id = _point_id("a.json", 0)
    removed_id = _point_id("a.json", 1)
    remaining_hash = _chunk_hash(remaining_chunk, "bge-base")

    manifest_path = tmp_path / "recipes.manifest.json"
    manifest_path.write_text(json.dumps({
        "embedding_model": "bge-base",
        "chunks": {remaining_id: remaining_hash, removed_id: "some-old-hash"},
    }))

    fake_embedder = _FakeEmbedder("bge-base")
    fake_db = _FakeVectorDB(RecipeRAGConfig())
    fake_db._count = 2

    import rag.embedder
    import rag.recipe_loader
    import rag.vector_database
    monkeypatch.setattr(rag.embedder, "TextEmbedder", lambda model_name: fake_embedder)
    monkeypatch.setattr(rag.recipe_loader, "load_recipe_sources", lambda paths: chunks)
    monkeypatch.setattr(rag.recipe_loader, "print_recipe_statistics", lambda chunks: None)
    monkeypatch.setattr(rag.vector_database, "QdrantVectorDB", lambda config: fake_db)

    pipeline, _ = _make_pipeline(tmp_path, chunks)
    pipeline.build_index()

    assert fake_db.created == []                # collection NOT recreated
    assert fake_embedder.calls == []             # nothing new/changed to embed
    assert fake_db.indexed_docs == []            # nothing to upsert
    assert fake_db.deleted_ids == [[removed_id]]  # exactly the removed chunk's id

    new_manifest = json.loads(manifest_path.read_text())["chunks"]
    assert set(new_manifest.keys()) == {remaining_id}


def _result(rerank_score=None, dense_score=None, score=0.0):
    r = {"score": score, "payload": {"title": "Test"}, "text": "### Test\n\n**Ingredients:**\nfoo"}
    if rerank_score is not None:
        r["rerank_score"] = rerank_score
    if dense_score is not None:
        r["dense_score"] = dense_score
    return r


def test_filter_grounded_uses_rerank_score_when_reranker_enabled():
    config = RecipeRAGConfig(USE_RERANKER=True, MIN_RERANK_SCORE=0.0)
    pipeline = RecipeRAGPipeline(config)

    results = [_result(rerank_score=5.0), _result(rerank_score=-3.0)]
    grounded = pipeline.filter_grounded(results)

    assert len(grounded) == 1
    assert grounded[0]["rerank_score"] == 5.0


def test_filter_grounded_falls_back_to_dense_score_when_reranker_disabled():
    config = RecipeRAGConfig(USE_RERANKER=False, MIN_DENSE_SCORE=0.6)
    pipeline = RecipeRAGPipeline(config)

    results = [_result(dense_score=0.8), _result(dense_score=0.3)]
    grounded = pipeline.filter_grounded(results)

    assert len(grounded) == 1
    assert grounded[0]["dense_score"] == 0.8


def test_find_recipes_or_generate_returns_corpus_matches_without_calling_llm():
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: [_result(rerank_score=5.0)]

    def fail_if_called(*args, **kwargs):
        raise AssertionError("generator should not be called when corpus matches exist")

    pipeline.generator = type("FakeGenerator", (), {"generate": fail_if_called})()

    result = pipeline.find_recipes_or_generate(["chicken", "rice"])

    assert result["source"] == "corpus"
    assert len(result["recipes"]) == 1
    assert result["generated"] is None


def test_find_recipes_or_generate_falls_back_to_llm_when_corpus_has_nothing():
    """Regression test: an earlier version of this endpoint just returned an empty list
    when nothing in the corpus matched, silently leaving the caller with nothing for an
    uncovered dish/cuisine (e.g. an obscure Russian dish not in the corpus)."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: []
    answers = iter([
        "### Kholodets\n\n**Ingredients:**\npork trotters, gelatin\n\n**Instructions:**\nSimmer and chill.",
        "### Pork Aspic Terrine\n\n**Ingredients:**\ncarrots\n\n**Instructions:**\nLayer and set.",
        "### Gelatin Consomme\n\n**Ingredients:**\nbroth\n\n**Instructions:**\nClarify and chill.",
    ])
    pipeline.generator = type("FakeGenerator", (), {"generate": lambda self, *a, **k: next(answers)})()

    result = pipeline.find_recipes_or_generate(["pork trotters", "gelatin"])

    assert result["source"] == "generated"
    assert result["error"] is None
    # Regression test: an earlier version asked the model for "3 recipes" in a single
    # completion, but the fine-tuned model always ignores that and returns exactly one
    # recipe regardless of the instruction (confirmed empirically, likely a fine-tuning
    # artifact rather than a prompt issue) — so a naive single-call approach silently
    # produced only 1 result even when 3 were requested. Making 3 separate calls fixes
    # this by working with the model's single-recipe habit instead of against it.
    assert len(result["recipes"]) == 3
    assert [r["title"] for r in result["recipes"]] == ["Kholodets", "Pork Aspic Terrine", "Gelatin Consomme"]
    assert all(r["rerank_score"] is None for r in result["recipes"])


def test_find_recipes_or_generate_uses_distinct_prompts_per_call():
    """Regression test: calling generate() with the identical question n times would hit
    the response cache and return the same recipe n times instead of n different ones —
    each call's question must differ."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: []
    seen_questions = []

    def fake_generate(self, question, context, system_prompt, **kwargs):
        seen_questions.append(question)
        return f"### Recipe {len(seen_questions)}\n\n**Ingredients:**\na\n\n**Instructions:**\ndo x"

    pipeline.generator = type("FakeGenerator", (), {"generate": fake_generate})()
    pipeline.find_recipes_or_generate(["chicken"], max_results=3)

    assert len(seen_questions) == 3
    assert len(set(seen_questions)) == 3  # all distinct


def test_find_recipes_or_generate_keeps_partial_results_on_mid_loop_failure():
    """One failed generation attempt (e.g. a transient network error) shouldn't wipe out
    suggestions that already succeeded."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: []
    call_count = [0]

    def flaky_generate(self, question, context, system_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise ConnectionError("simulated transient failure")
        return f"### Recipe {call_count[0]}\n\n**Ingredients:**\na\n\n**Instructions:**\ndo x"

    pipeline.generator = type("FakeGenerator", (), {"generate": flaky_generate})()
    result = pipeline.find_recipes_or_generate(["chicken"], max_results=3)

    assert result["source"] == "generated"
    assert len(result["recipes"]) == 2
    assert result["error"] is None  # partial success isn't reported as an error


def test_split_generated_recipes_parses_multiple_recipe_blocks():
    text = (
        "### Recipe One\n\n**Ingredients:**\na, b\n\n**Instructions:**\ndo x\n\n"
        "### Recipe Two\n\n**Ingredients:**\nc, d\n\n**Instructions:**\ndo y"
    )
    recipes = _split_generated_recipes(text)

    assert len(recipes) == 2
    assert recipes[0]["title"] == "Recipe One"
    assert recipes[1]["title"] == "Recipe Two"
    assert recipes[0]["text"].startswith("### Recipe One")


def test_split_generated_recipes_handles_single_recipe():
    text = "### Only Recipe\n\n**Ingredients:**\na\n\n**Instructions:**\ndo x"
    recipes = _split_generated_recipes(text)

    assert len(recipes) == 1
    assert recipes[0]["title"] == "Only Recipe"


def test_split_generated_recipes_handles_malformed_text_without_heading():
    """If the model ignores the '### Title' instruction, don't crash — just return no
    parsed recipes rather than guessing at a title from unstructured text."""
    assert _split_generated_recipes("just some free text with no heading at all") == []


def test_find_recipes_or_generate_reports_error_instead_of_raising():
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: []

    def broken_generate(*args, **kwargs):
        raise ConnectionError("simulated failure")

    pipeline.generator = type("FakeGenerator", (), {"generate": broken_generate})()

    result = pipeline.find_recipes_or_generate(["pork trotters", "gelatin"])

    assert result["source"] == "generated"
    assert result["generated"] is None
    assert "simulated failure" in result["error"]


# ---------------------------------------------------------------------------
# normalize=False must be the default and must NOT run normalize_grocery_heading() --
# regression tests for the confirmed corruption an adversarial review found when
# normalization ran unconditionally on arbitrary user-typed free text (see
# grocery_terms.py's suffix/noise-token matching, validated only against real
# Norwegian Tjek headings, never English vocabulary).
# ---------------------------------------------------------------------------

# The exact 6 adversarial examples confirmed live against normalize_grocery_heading()
# before this fix: real English ingredient phrases a user could type on the
# Ingredients screen, each silently corrupted by a glossary/noise-token suffix
# collision (e.g. "scoop" matching the "coop" store-noise word, "clam" mistranslated
# via a suffix match onto the lamb glossary entry, etc).
ADVERSARIAL_ENGLISH_INGREDIENTS = [
    "extra virgin olive oil",
    "clam chowder with bacon",
    "ghost pepper, garlic, lime",
    "defrost the chicken breast",
    "corn cobs",
    "a scoop of vanilla ice cream",
]


def test_find_recipes_from_ingredients_defaults_to_no_normalization():
    """normalize must default to False -- restoring the pre-existing safe behavior for
    the general (non-Tjek) case, not the unconditional normalization this whole
    regression was about."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    seen_queries = []
    pipeline.retrieve = lambda query, top_k=None: (seen_queries.append(query) or [])

    for ingredient in ADVERSARIAL_ENGLISH_INGREDIENTS:
        pipeline.find_recipes_from_ingredients([ingredient])

    # Every adversarial example must reach retrieve() byte-for-byte unchanged --
    # proving find_recipes_from_ingredients() does NOT call
    # normalize_grocery_heading() when normalize is omitted (the default).
    assert seen_queries == ADVERSARIAL_ENGLISH_INGREDIENTS


def test_find_recipes_from_ingredients_normalize_true_still_normalizes():
    """normalize=True must still route ingredients through
    normalize_grocery_heading() -- this is the behavior /recipes/discounted relies on
    for real Tjek product names (e.g. Norwegian flyer headings), so the fix must not
    have thrown out the working case while closing the free-text hole."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    seen_queries = []
    pipeline.retrieve = lambda query, top_k=None: (seen_queries.append(query) or [])

    pipeline.find_recipes_from_ingredients(["REKER I LØSVEKT"], normalize=True)

    assert len(seen_queries) == 1
    assert "shrimp" in seen_queries[0].lower()
    assert "reker" not in seen_queries[0].lower()


def test_find_recipes_or_generate_does_not_corrupt_english_free_text_by_default():
    """End-to-end regression test for the exact 6 adversarial examples confirmed live:
    each one must be returned to the LLM-generation prompt COMPLETELY UNCHANGED when
    normalize=False (the default), proving find_recipes_or_generate() no longer
    corrupts arbitrary user-typed ingredients."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: []
    seen_questions = []

    def fake_generate(self, question, context, system_prompt, **kwargs):
        seen_questions.append(question)
        return f"### Recipe {len(seen_questions)}\n\n**Ingredients:**\na\n\n**Instructions:**\ndo x"

    pipeline.generator = type("FakeGenerator", (), {"generate": fake_generate})()

    for ingredient in ADVERSARIAL_ENGLISH_INGREDIENTS:
        seen_questions.clear()
        pipeline.find_recipes_or_generate([ingredient], max_results=1)
        assert ingredient in seen_questions[0]


def test_find_recipes_or_generate_normalize_true_still_normalizes_generation_prompt():
    """normalize=True must still translate Norwegian flyer headings before the
    generation-fallback prompt too (not just retrieval) -- otherwise
    /recipes/discounted regresses to the original raw-Norwegian-text hallucination
    bug this module was built to fix."""
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10, normalize=False: []
    seen_questions = []

    def fake_generate(self, question, context, system_prompt, **kwargs):
        seen_questions.append(question)
        return "### Shrimp Stir Fry\n\n**Ingredients:**\nshrimp\n\n**Instructions:**\ndo x"

    pipeline.generator = type("FakeGenerator", (), {"generate": fake_generate})()

    pipeline.find_recipes_or_generate(["REKER I LØSVEKT"], max_results=1, normalize=True)

    assert "shrimp" in seen_questions[0]
    assert "REKER" not in seen_questions[0]

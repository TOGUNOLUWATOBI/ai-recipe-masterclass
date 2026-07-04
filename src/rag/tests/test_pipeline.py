"""Tests for pipeline.py's pure logic — _content_hash and filter_grounded — without
touching the real embedder/Qdrant/generator (those need models and a live corpus)."""

from rag.config import RecipeRAGConfig
from rag.pipeline import RecipeRAGPipeline, _content_hash, _split_generated_recipes


def _chunk(text, source="a.json", chunk_id=0):
    return {"text": text, "source_file": source, "chunk_id": chunk_id}


def test_content_hash_is_deterministic():
    chunks = [_chunk("### Jollof Rice\n\nA"), _chunk("### Egusi Soup\n\nB", chunk_id=1)]
    assert _content_hash(chunks, "model-x") == _content_hash(chunks, "model-x")


def test_content_hash_changes_when_content_changes_even_with_same_count():
    """Regression test for the exact bug found this session: comparing only the recipe
    count silently kept serving stale embeddings when a recipe's text changed but the
    total number of recipes stayed the same."""
    original = [_chunk("### Jollof Rice\n\nOriginal ingredients")]
    edited = [_chunk("### Jollof Rice\n\nCompletely different ingredients")]

    assert len(original) == len(edited)  # same count...
    assert _content_hash(original, "model-x") != _content_hash(edited, "model-x")  # ...different hash


def test_content_hash_changes_when_embedding_model_changes():
    """Regression test: switching MiniLM -> bge-base needed a manual force_rebuild the
    first time, because the old check didn't know the embedding model itself had changed."""
    chunks = [_chunk("### Jollof Rice\n\nA")]
    assert _content_hash(chunks, "minilm") != _content_hash(chunks, "bge-base")


def test_content_hash_order_independent():
    """Sorted internally by (source_file, chunk_id) — hash shouldn't depend on the
    order load_recipe_sources happened to produce chunks in."""
    a = [_chunk("### A\n\nfoo", chunk_id=0), _chunk("### B\n\nbar", chunk_id=1)]
    b = list(reversed(a))
    assert _content_hash(a, "model-x") == _content_hash(b, "model-x")


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
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10: [_result(rerank_score=5.0)]

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
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10: []
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
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10: []
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
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10: []
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
    pipeline.find_recipes_from_ingredients = lambda ingredients, max_results=10: []

    def broken_generate(*args, **kwargs):
        raise ConnectionError("simulated failure")

    pipeline.generator = type("FakeGenerator", (), {"generate": broken_generate})()

    result = pipeline.find_recipes_or_generate(["pork trotters", "gelatin"])

    assert result["source"] == "generated"
    assert result["generated"] is None
    assert "simulated failure" in result["error"]

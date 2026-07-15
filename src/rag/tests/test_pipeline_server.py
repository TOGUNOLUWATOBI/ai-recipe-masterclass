"""Tests for pipeline_server.py's FastAPI route handlers -- specifically the
`normalize` flag contract between the two /recipes routes and pipeline.py's
find_recipes_or_generate(): /recipes/from-ingredients must forward the request's
is_grocery_product flag (default False, safe for arbitrary user free text) while
/recipes/discounted must always pass normalize=True unconditionally (its product list
is always real Tjek data, never user input -- no request-side flag needed).

Skipped entirely (not failed) in any environment without fastapi installed -- this
service is deliberately split from the retrieval service specifically so the
retrieval-only container never needs fastapi's sibling ML deps; see pipeline.py's
module docstring and requirements-retrieval.txt vs. requirements-pipeline.txt for the
same split this respects."""

import asyncio

import pytest

pytest.importorskip("fastapi")

from rag import pipeline_server  # noqa: E402
from rag.pipeline_server import (  # noqa: E402
    IngredientsRequest,
    QueryRequest,
    query,
    query_stream,
    recipes_discounted,
    recipes_from_ingredients,
)


def _fake_result():
    return {"source": "corpus", "recipes": [], "generated": None, "error": None}


def test_ingredients_request_is_grocery_product_defaults_to_false():
    """Contract with the mobile client: is_grocery_product must default to False so a
    request that omits it (as IngredientsScreen's arbitrary free-text search does)
    gets the safe, non-normalizing behavior."""
    req = IngredientsRequest(ingredients=["clam chowder with bacon"])
    assert req.is_grocery_product is False


def test_recipes_from_ingredients_forwards_is_grocery_product_false_by_default(monkeypatch):
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["normalize"] = normalize
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)

    recipes_from_ingredients(IngredientsRequest(ingredients=["clam chowder with bacon"]))

    assert seen["normalize"] is False


def test_recipes_from_ingredients_forwards_is_grocery_product_true(monkeypatch):
    """DealDetailScreen's contract: is_grocery_product=True must reach
    find_recipes_or_generate() as normalize=True, since its ingredient is always a
    real Tjek product name."""
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["normalize"] = normalize
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)

    recipes_from_ingredients(IngredientsRequest(
        ingredients=["COOP GRILL PERFEKT BOKEROKTE SOMMERKOTELETTER"], is_grocery_product=True,
    ))

    assert seen["normalize"] is True


def test_recipes_discounted_always_normalizes_unconditionally(monkeypatch):
    """/recipes/discounted has no request-side flag -- its product_name list is always
    sourced from the real Tjek discounts snapshot, so normalize=True must be passed
    every time, regardless of what's in the snapshot."""
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["normalize"] = normalize
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "REKER I LØSVEKT"}], "2026-07-09T06:00:00+00:00"),
    )

    recipes_discounted(max_results=10, include_recipes=True)

    assert seen["normalize"] is True


def test_recipes_discounted_treats_a_present_but_none_category_as_main_food(monkeypatch):
    """Regression test: get_latest_snapshot() always includes a "category" key (it's one
    of discounts_store._COLUMNS) -- for a row scanned before this column existed, its
    value is None, not an absent key. A naive `d.get("category", "main_food")` would
    never actually fall back (the key is present), silently treating every such row as
    excluded and returning zero recipes right after this feature's own DB migration
    until the next scheduled Tjek sweep repopulates real categories."""
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["ingredients"] = ingredients
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "REKER I LØSVEKT", "category": None}], "2026-07-15T06:00:00+00:00"),
    )

    result = recipes_discounted(max_results=10, include_recipes=True)

    assert seen["ingredients"] == ["REKER I LØSVEKT"]
    assert result["recipes"] == []  # from _fake_result(), not the empty-skip path


def test_recipes_discounted_excludes_non_main_food_from_the_recipe_query(monkeypatch):
    """Snack and non-food items stay in discounted_ingredients (the app shows them in
    their own tab/menu) but must never reach find_recipes_or_generate() -- neither is a
    sensible recipe ingredient."""
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["ingredients"] = ingredients
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: (
            [
                {"product_name": "KYLLINGFILET", "category": "main_food"},
                {"product_name": "FREIA MELKESJOKOLADE", "category": "snack"},
                {"product_name": "LAMBI TOALETTPAPIR", "category": "non_food"},
            ],
            "2026-07-15T06:00:00+00:00",
        ),
    )

    result = recipes_discounted(max_results=10, include_recipes=True)

    assert seen["ingredients"] == ["KYLLINGFILET"]
    # the full, unfiltered list (all three categories) is still returned for the app
    assert len(result["discounted_ingredients"]) == 3


def test_recipes_discounted_skips_generation_pass_when_nothing_is_main_food(monkeypatch):
    """If every currently-cached item happens to be a snack/non-food (e.g. right after
    a scan dominated by candy aisle offers), there's nothing sensible to feed the recipe
    generator -- must skip that call entirely rather than pass an empty ingredient list
    into it."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("find_recipes_or_generate should not be called with no main_food items")

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fail_if_called)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "FREIA MELKESJOKOLADE", "category": "snack"}], "2026-07-15T06:00:00+00:00"),
    )

    result = recipes_discounted(max_results=10, include_recipes=True)

    assert result["recipes"] == []
    assert result["source"] is None
    assert len(result["discounted_ingredients"]) == 1


def test_recipes_discounted_skips_generation_pass_when_include_recipes_false(monkeypatch):
    """include_recipes=false must return immediately without calling
    find_recipes_or_generate() at all (fast path for a deals-browsing UI) -- confirm
    normalize's default-True fix didn't accidentally start invoking generation on this
    path."""
    def fail_if_called(*args, **kwargs):
        raise AssertionError("find_recipes_or_generate should not be called when include_recipes=False")

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fail_if_called)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "REKER I LØSVEKT"}], "2026-07-09T06:00:00+00:00"),
    )

    result = recipes_discounted(max_results=10, include_recipes=False)

    assert result["recipes"] == []
    assert result["source"] is None


# ---------------------------------------------------------------------------
# Language (EN/NO) passthrough -- all three generation-touching routes forward
# QueryRequest/IngredientsRequest's language field straight to the pipeline; the
# request models default it to "en" so existing clients that never send it (or the
# mobile app before it's updated to send one) keep today's English-only behavior.
# ---------------------------------------------------------------------------

def test_query_request_language_defaults_to_english():
    assert QueryRequest(question="what's for dinner?").language == "en"


def test_ingredients_request_language_defaults_to_english():
    assert IngredientsRequest(ingredients=["chicken"]).language == "en"


def test_query_forwards_language_to_run_query(monkeypatch):
    seen = {}

    def fake_run_query(question, top_k=None, language="en"):
        seen["language"] = language
        return {"question": question, "retrieved": [], "grounded": [], "context": "", "answer": "hei", "error": None, "elapsed": 0.1}

    monkeypatch.setattr(pipeline_server.pipeline, "run_query", fake_run_query)

    query(QueryRequest(question="hva kan jeg lage?", language="no"))

    assert seen["language"] == "no"


def test_query_defaults_to_english_when_not_specified(monkeypatch):
    seen = {}

    def fake_run_query(question, top_k=None, language="en"):
        seen["language"] = language
        return {"question": question, "retrieved": [], "grounded": [], "context": "", "answer": "hi", "error": None, "elapsed": 0.1}

    monkeypatch.setattr(pipeline_server.pipeline, "run_query", fake_run_query)

    query(QueryRequest(question="what can I cook?"))

    assert seen["language"] == "en"


def test_query_stream_forwards_language_to_run_query_stream(monkeypatch):
    seen = {}

    def fake_run_query_stream(question, top_k=None, language="en"):
        seen["language"] = language
        yield {"type": "chunk", "text": "hei"}

    monkeypatch.setattr(pipeline_server.pipeline, "run_query_stream", fake_run_query_stream)

    response = query_stream(QueryRequest(question="hva kan jeg lage?", language="no"))

    async def consume():
        async for _ in response.body_iterator:
            pass

    asyncio.run(consume())

    assert seen["language"] == "no"


def test_recipes_from_ingredients_forwards_language(monkeypatch):
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["language"] = language
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)

    recipes_from_ingredients(IngredientsRequest(ingredients=["kylling"], language="no"))

    assert seen["language"] == "no"


def test_recipes_discounted_forwards_language(monkeypatch):
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["language"] = language
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "KYLLINGFILET", "category": "main_food"}], "2026-07-15T06:00:00+00:00"),
    )

    recipes_discounted(max_results=10, include_recipes=True, language="no")

    assert seen["language"] == "no"


def test_recipes_discounted_defaults_to_english_language(monkeypatch):
    seen = {}

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False, language="en"):
        seen["language"] = language
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "KYLLINGFILET", "category": "main_food"}], "2026-07-15T06:00:00+00:00"),
    )

    recipes_discounted(max_results=10, include_recipes=True)

    assert seen["language"] == "en"

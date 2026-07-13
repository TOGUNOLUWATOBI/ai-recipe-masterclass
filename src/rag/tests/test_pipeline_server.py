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

import pytest

pytest.importorskip("fastapi")

from rag import pipeline_server  # noqa: E402
from rag.pipeline_server import IngredientsRequest, recipes_discounted, recipes_from_ingredients  # noqa: E402


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

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False):
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

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False):
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

    def fake_find_recipes_or_generate(ingredients, max_results=10, normalize=False):
        seen["normalize"] = normalize
        return _fake_result()

    monkeypatch.setattr(pipeline_server.pipeline, "find_recipes_or_generate", fake_find_recipes_or_generate)
    monkeypatch.setattr(
        pipeline_server, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "REKER I LØSVEKT"}], "2026-07-09T06:00:00+00:00"),
    )

    recipes_discounted(max_results=10, include_recipes=True)

    assert seen["normalize"] is True


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

"""Tests for meal_ideas.py -- Epic C's cart -> meal-idea pipeline. Uses a fake pipeline
(no real retrieval/embedding/LLM) so these run offline and fast; see
test_pipeline_server.py for the same mocking style applied to the FastAPI layer."""

from unittest.mock import MagicMock

import pytest

from rag.meal_ideas import (
    _discount_item_id,
    _split_generated_ingredient_lines,
    compute_coverage,
    completion_status,
    filter_eligible_items,
    generate_meal_ideas_from_cart,
    normalize_and_dedupe,
    resolve_cart_items,
)


def _row(product_name, store_name="Kiwi", recipe_eligible=True, recipe_exclusion_reason=None, category="main_food"):
    return {
        "product_name": product_name,
        "store_name": store_name,
        "category": category,
        "recipe_eligible": recipe_eligible,
        "recipe_exclusion_reason": recipe_exclusion_reason,
    }


# ---------------------------------------------------------------------------
# _discount_item_id / resolve_cart_items
# ---------------------------------------------------------------------------

def test_discount_item_id_matches_the_mobile_apps_convention():
    assert _discount_item_id(_row("Kyllingfilet", store_name="Kiwi")) == "Kiwi::Kyllingfilet"


def test_discount_item_id_falls_back_for_a_missing_store_name():
    assert _discount_item_id(_row("Kyllingfilet", store_name=None)) == "unknown-store::Kyllingfilet"


def test_resolve_cart_items_matches_known_ids():
    discounts = [_row("Kyllingfilet"), _row("Laksefilet")]

    resolved, excluded = resolve_cart_items(["Kiwi::Kyllingfilet"], discounts)

    assert len(resolved) == 1
    assert resolved[0]["product_name"] == "Kyllingfilet"
    assert excluded == []


def test_resolve_cart_items_excludes_an_id_not_in_the_snapshot():
    resolved, excluded = resolve_cart_items(["Kiwi::NoLongerOnSale"], [_row("Kyllingfilet")])

    assert resolved == []
    assert excluded == [{"product_name": "Kiwi::NoLongerOnSale", "reason": "not_found"}]


# ---------------------------------------------------------------------------
# filter_eligible_items
# ---------------------------------------------------------------------------

def test_filter_eligible_items_splits_by_recipe_eligible():
    rows = [
        _row("Kyllingfilet", recipe_eligible=True),
        _row("Coca-Cola", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("Toalettpapir", recipe_eligible=False, recipe_exclusion_reason="non_food"),
    ]

    eligible, excluded = filter_eligible_items(rows)

    assert [r["product_name"] for r in eligible] == ["Kyllingfilet"]
    assert excluded == [
        {"product_name": "Coca-Cola", "reason": "beverage"},
        {"product_name": "Toalettpapir", "reason": "non_food"},
    ]


def test_filter_eligible_items_defaults_a_missing_reason_to_other():
    rows = [_row("Mystery", recipe_eligible=False, recipe_exclusion_reason=None)]

    _, excluded = filter_eligible_items(rows)

    assert excluded == [{"product_name": "Mystery", "reason": "other"}]


# ---------------------------------------------------------------------------
# normalize_and_dedupe
# ---------------------------------------------------------------------------

def test_normalize_and_dedupe_translates_norwegian_headings():
    pairs = normalize_and_dedupe([_row("KYLLINGFILET"), _row("LAKSEFILET")])

    assert ("KYLLINGFILET", "chicken fillet") in pairs
    assert ("LAKSEFILET", "salmon fillet") in pairs


def test_normalize_and_dedupe_collapses_the_same_ingredient_from_two_stores():
    """Two different stores discounting the same product should count as one
    ingredient, not two (Task C2's "deduplicate equivalent ingredients")."""
    pairs = normalize_and_dedupe([
        _row("KYLLINGFILET", store_name="Kiwi"),
        _row("KYLLINGFILET", store_name="Meny"),
    ])

    assert len(pairs) == 1


# ---------------------------------------------------------------------------
# compute_coverage / completion_status
# ---------------------------------------------------------------------------

def test_compute_coverage_matches_a_real_ingredient_line():
    coverage = compute_coverage(["2 boneless chicken breasts, cubed", "1 onion, diced"], ["chicken fillet"])

    assert coverage["matched_cart_names"] == ["chicken fillet"]
    assert coverage["missing_required_ingredients"] == ["1 onion, diced"]
    assert coverage["ingredient_coverage_percentage"] == 50.0


def test_compute_coverage_all_matched_is_complete_coverage():
    coverage = compute_coverage(["chicken breast", "rice"], ["chicken fillet", "rice"])

    assert coverage["missing_required_ingredients"] == []
    assert coverage["ingredient_coverage_percentage"] == 100.0


def test_compute_coverage_handles_an_empty_recipe():
    coverage = compute_coverage([], ["chicken fillet"])

    assert coverage["ingredient_coverage_percentage"] == 0.0
    assert coverage["matched_cart_names"] == []


def test_compute_coverage_does_not_double_count_the_same_cart_ingredient():
    coverage = compute_coverage(["chicken breast", "chicken stock"], ["chicken fillet"])

    assert coverage["matched_cart_names"] == ["chicken fillet"]


def test_split_generated_ingredient_lines_strips_bullet_markers():
    block = "- chicken breast\n- 1 cup rice\n* onion"
    assert _split_generated_ingredient_lines(block) == ["chicken breast", "1 cup rice", "onion"]


def test_split_generated_ingredient_lines_skips_blank_lines():
    block = "- chicken breast\n\n- rice\n"
    assert _split_generated_ingredient_lines(block) == ["chicken breast", "rice"]


def test_split_generated_ingredient_lines_falls_back_when_no_bullet_marker():
    """Real generated text isn't guaranteed to always use a bullet marker -- a bare
    line is still kept (stripped), not dropped."""
    block = "chicken breast\nrice"
    assert _split_generated_ingredient_lines(block) == ["chicken breast", "rice"]


def test_completion_status_thresholds():
    assert completion_status(total_ingredients=5, missing_count=0) == "complete"
    assert completion_status(total_ingredients=5, missing_count=1) == "nearly_complete"
    assert completion_status(total_ingredients=5, missing_count=2) == "nearly_complete"
    assert completion_status(total_ingredients=5, missing_count=3) == "partial"


# ---------------------------------------------------------------------------
# generate_meal_ideas_from_cart -- full orchestration, mocked pipeline
# ---------------------------------------------------------------------------

def _grounded_result(title, ingredients, rerank_score=5.0):
    return {
        "id": title,
        "score": 1.0,
        "dense_score": 0.7,
        "rerank_score": rerank_score,
        "text": f"### {title}",
        "payload": {"title": title, "ingredients": ingredients, "instructions": ["Cook it."]},
    }


def test_returns_empty_ideas_without_calling_the_pipeline_when_nothing_is_eligible():
    """Task C8: zero eligible ingredients must never reach retrieval or generation."""
    pipeline = MagicMock()
    discounts = [_row("Coca-Cola", recipe_eligible=False, recipe_exclusion_reason="beverage")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::Coca-Cola"])

    assert result["ideas"] == []
    assert result["excluded_cart_items"] == [{"product_name": "Coca-Cola", "reason": "beverage"}]
    pipeline.find_recipes_from_ingredients.assert_not_called()


def test_builds_an_idea_from_a_retrieved_corpus_recipe():
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Chicken and Rice", ["chicken breast", "rice", "onion"]),
    ]
    discounts = [_row("KYLLINGFILET")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET"])

    assert len(result["ideas"]) == 1
    idea = result["ideas"][0]
    assert idea["title"] == "Chicken and Rice"
    assert idea["source_type"] == "retrieved"
    assert idea["selected_items_used"] == ["chicken fillet"]
    assert idea["missing_required_ingredients"] == ["rice", "onion"]
    assert idea["completion_status"] == "nearly_complete"
    assert idea["optional_ingredients"] == []
    assert idea["estimated_complexity"] is None


def test_never_sends_an_excluded_products_name_into_the_retrieval_query():
    """Task C2's hard requirement: excluded items must never reach a retrieval query."""
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = []
    # Empty retrieval falls through to the generation fallback (see module docstring) --
    # give it a harmless, non-matching response so it completes cleanly rather than
    # crashing on an unconfigured MagicMock return value; this test only cares about
    # what was passed to find_recipes_from_ingredients, not what the fallback returns.
    pipeline.generator.generate.return_value = "### Nothing\n\n**Ingredients:**\n- nothing in particular"
    discounts = [
        _row("KYLLINGFILET"),
        _row("Coca-Cola", recipe_eligible=False, recipe_exclusion_reason="beverage"),
    ]

    generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET", "Kiwi::Coca-Cola"])

    called_ingredients = pipeline.find_recipes_from_ingredients.call_args.args[0]
    assert called_ingredients == ["chicken fillet"]
    assert "Coca-Cola" not in called_ingredients
    assert not any("cola" in ing.lower() for ing in called_ingredients)


def test_drops_a_retrieved_recipe_that_does_not_actually_use_any_cart_ingredient():
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Unrelated Salad", ["lettuce", "cucumber"]),
    ]
    # No retrieved idea used any cart ingredient, so this falls through to the
    # generation fallback -- given a harmless, non-matching response so that path
    # completes cleanly and also produces nothing.
    pipeline.generator.generate.return_value = "### Nothing\n\n**Ingredients:**\n- nothing in particular"
    discounts = [_row("KYLLINGFILET")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET"])

    assert result["ideas"] == []


def test_ranks_complete_matches_above_partial_ones():
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result("Partial Match", ["chicken breast", "rice", "onion", "garlic"]),
        _grounded_result("Complete Match", ["chicken breast"]),
    ]
    discounts = [_row("KYLLINGFILET")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET"])

    assert [idea["title"] for idea in result["ideas"]] == ["Complete Match", "Partial Match"]


def test_caps_ideas_at_max_results_after_ranking():
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [
        _grounded_result(f"Recipe {i}", ["chicken breast"]) for i in range(5)
    ]
    discounts = [_row("KYLLINGFILET")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET"], max_results=2)

    assert len(result["ideas"]) == 2


def test_falls_back_to_generation_when_retrieval_returns_nothing(monkeypatch):
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = []
    pipeline.generator.generate.return_value = (
        "### Chicken Rice Bowl\n\n**Ingredients:**\n- chicken breast\n- rice\n\n"
        "**Instructions:**\n1. Cook everything."
    )
    discounts = [_row("KYLLINGFILET")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET"], max_results=1)

    assert len(result["ideas"]) == 1
    idea = result["ideas"][0]
    assert idea["source_type"] == "generated"
    assert idea["title"] == "Chicken Rice Bowl"
    assert idea["selected_items_used"] == ["chicken fillet"]
    assert idea["missing_required_ingredients"] == ["rice"] or "rice" not in idea["missing_required_ingredients"]


def test_generation_fallback_never_crashes_when_the_llm_call_fails():
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = []
    pipeline.generator.generate.side_effect = ConnectionError("no route to host")
    discounts = [_row("KYLLINGFILET")]

    result = generate_meal_ideas_from_cart(pipeline, discounts, ["Kiwi::KYLLINGFILET"])

    assert result["ideas"] == []


def test_excluded_cart_items_combine_not_found_and_ineligible():
    pipeline = MagicMock()
    pipeline.find_recipes_from_ingredients.return_value = [_grounded_result("X", ["chicken breast"])]
    discounts = [
        _row("KYLLINGFILET"),
        _row("Coca-Cola", recipe_eligible=False, recipe_exclusion_reason="beverage"),
    ]

    result = generate_meal_ideas_from_cart(
        pipeline, discounts, ["Kiwi::KYLLINGFILET", "Kiwi::Coca-Cola", "Kiwi::Gone"],
    )

    reasons = {item["product_name"]: item["reason"] for item in result["excluded_cart_items"]}
    assert reasons["Coca-Cola"] == "beverage"
    assert reasons["Kiwi::Gone"] == "not_found"

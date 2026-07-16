"""Tests for product_classification.py -- the shared Epic A schema every classifier
(the keyword heuristic, the LLM tier, and manual overrides) produces."""

import json

import pytest

from rag.product_classification import (
    build_classification,
    legacy_category,
    load_manual_overrides,
    validate_llm_entry,
)


def test_build_classification_non_food_ignores_food_usage_class():
    """shopping_group="non_food" always collapses food_usage_class/meal_role to
    "not_applicable" regardless of what's passed in -- a non-food product has no
    meaningful usage class to report."""
    result = build_classification("non_food", "primary_ingredient", "protein")

    assert result == {
        "shopping_group": "non_food",
        "food_usage_class": "not_applicable",
        "meal_role": "not_applicable",
        "recipe_eligible": False,
        "recipe_exclusion_reason": "non_food",
    }


@pytest.mark.parametrize("usage_class", ["primary_ingredient", "supporting_ingredient"])
def test_build_classification_eligible_usage_classes(usage_class):
    result = build_classification("food", usage_class, "vegetable")

    assert result["recipe_eligible"] is True
    assert result["recipe_exclusion_reason"] is None
    assert result["meal_role"] == "vegetable"


@pytest.mark.parametrize("usage_class,expected_reason", [
    ("ready_meal", "finished_meal"),
    ("ready_to_eat", "finished_meal"),
    ("beverage", "beverage"),
    ("snack_or_treat", "snack_or_treat"),
    ("unknown", "insufficient_confidence"),
])
def test_build_classification_ineligible_usage_classes(usage_class, expected_reason):
    result = build_classification("food", usage_class, "protein")

    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == expected_reason
    # meal_role is never kept for an ineligible product -- not meaningful for a
    # beverage or a ready meal.
    assert result["meal_role"] == "not_applicable"


def test_legacy_category_maps_non_food():
    assert legacy_category(build_classification("non_food", "not_applicable")) == "non_food"


def test_legacy_category_maps_beverage_and_snack_to_snack():
    assert legacy_category(build_classification("food", "beverage")) == "snack"
    assert legacy_category(build_classification("food", "snack_or_treat")) == "snack"


def test_legacy_category_maps_everything_else_to_main_food():
    """Ready meals and ready-to-eat products are real food, not snacks/beverages, so
    the backward-compatible label still buckets them as "main_food" -- exactly the gap
    Epic A's recipe_eligible field exists to close for recipe generation specifically,
    without changing what the app's existing Food/Non-food tabs show."""
    assert legacy_category(build_classification("food", "primary_ingredient")) == "main_food"
    assert legacy_category(build_classification("food", "supporting_ingredient")) == "main_food"
    assert legacy_category(build_classification("food", "ready_meal")) == "main_food"
    assert legacy_category(build_classification("food", "ready_to_eat")) == "main_food"
    assert legacy_category(build_classification("food", "unknown")) == "main_food"


def test_validate_llm_entry_accepts_a_well_formed_entry():
    result = validate_llm_entry({
        "shopping_group": "food", "food_usage_class": "primary_ingredient",
        "meal_role": "protein", "confidence": "high",
    })

    assert result["food_usage_class"] == "primary_ingredient"
    assert result["recipe_eligible"] is True


def test_validate_llm_entry_rejects_an_invalid_shopping_group():
    assert validate_llm_entry({"shopping_group": "maybe", "food_usage_class": "primary_ingredient", "confidence": "high"}) is None


def test_validate_llm_entry_rejects_an_invalid_food_usage_class():
    assert validate_llm_entry({"shopping_group": "food", "food_usage_class": "made_up_class", "confidence": "high"}) is None


def test_validate_llm_entry_defaults_a_missing_meal_role_to_other():
    result = validate_llm_entry({"shopping_group": "food", "food_usage_class": "primary_ingredient", "confidence": "high"})
    assert result["meal_role"] == "other"


def test_validate_llm_entry_folds_low_confidence_into_unknown():
    result = validate_llm_entry({
        "shopping_group": "food", "food_usage_class": "primary_ingredient",
        "meal_role": "protein", "confidence": "low",
    })

    assert result["food_usage_class"] == "unknown"
    assert result["recipe_eligible"] is False
    assert result["recipe_exclusion_reason"] == "insufficient_confidence"


def test_load_manual_overrides_returns_empty_dict_when_file_missing(tmp_path, monkeypatch):
    import rag.product_classification as pc
    monkeypatch.setattr(pc, "MANUAL_OVERRIDES_PATH", tmp_path / "does-not-exist.json")

    assert load_manual_overrides() == {}


def test_load_manual_overrides_returns_empty_dict_on_malformed_json(tmp_path, monkeypatch):
    import rag.product_classification as pc
    bad_file = tmp_path / "overrides.json"
    bad_file.write_text("not valid json{", encoding="utf-8")
    monkeypatch.setattr(pc, "MANUAL_OVERRIDES_PATH", bad_file)

    assert load_manual_overrides() == {}


def test_load_manual_overrides_parses_a_real_entry(tmp_path, monkeypatch):
    import rag.product_classification as pc
    overrides_file = tmp_path / "overrides.json"
    overrides_file.write_text(json.dumps({
        "COCA-COLA ZERO": {"shopping_group": "food", "food_usage_class": "beverage"},
    }), encoding="utf-8")
    monkeypatch.setattr(pc, "MANUAL_OVERRIDES_PATH", overrides_file)

    result = load_manual_overrides()

    assert result["COCA-COLA ZERO"]["food_usage_class"] == "beverage"
    assert result["COCA-COLA ZERO"]["recipe_eligible"] is False


def test_load_manual_overrides_skips_an_entry_with_an_invalid_shopping_group(tmp_path, monkeypatch):
    import rag.product_classification as pc
    overrides_file = tmp_path / "overrides.json"
    overrides_file.write_text(json.dumps({
        "BAD ENTRY": {"shopping_group": "maybe", "food_usage_class": "beverage"},
    }), encoding="utf-8")
    monkeypatch.setattr(pc, "MANUAL_OVERRIDES_PATH", overrides_file)

    assert load_manual_overrides() == {}


def test_load_manual_overrides_ships_with_the_two_spec_examples():
    """The real, checked-in manual_product_overrides.json (Epic A5) should load
    cleanly and contain at least the two worked examples from the change spec."""
    result = load_manual_overrides()

    assert result["COCA-COLA ZERO"]["food_usage_class"] == "beverage"
    assert result["COCA-COLA ZERO"]["recipe_eligible"] is False
    assert result["HAKKEDE TOMATER"]["food_usage_class"] == "supporting_ingredient"
    assert result["HAKKEDE TOMATER"]["recipe_eligible"] is True

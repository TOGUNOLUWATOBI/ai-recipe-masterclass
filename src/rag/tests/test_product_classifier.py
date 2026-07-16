"""Tests for product_classifier.py -- the LLM-based classification step that upgrades
grocery_discounts.py's keyword-heuristic classification for products
discounts_store's product_classifications cache hasn't seen before. Uses a fake
generator (no real Ollama call) so these run offline and fast; see the module
docstring for why any failure here must degrade to "leave this product unclassified"
rather than guessing or crashing."""

import json

import pytest

from rag.product_classifier import _build_prompt, classify_batch, classify_new_products


class _FakeGenerator:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self._raises:
            raise self._raises
        return self._response


def _entry(index, shopping_group="food", food_usage_class="primary_ingredient", meal_role="other", confidence="high"):
    return {
        "index": index,
        "shopping_group": shopping_group,
        "food_usage_class": food_usage_class,
        "meal_role": meal_role,
        "confidence": confidence,
    }


def _classifications_response(entries):
    return json.dumps({"classifications": entries})


def test_build_prompt_numbers_each_product_starting_at_one():
    prompt = _build_prompt(["KYLLINGFILET", "Kvikk Lunsj"])
    assert "1. KYLLINGFILET" in prompt
    assert "2. Kvikk Lunsj" in prompt


def test_classify_batch_returns_empty_dict_for_empty_input():
    generator = _FakeGenerator()
    assert classify_batch(generator, []) == {}
    assert generator.calls == []


def test_classify_batch_maps_indices_back_to_product_names():
    generator = _FakeGenerator(response=_classifications_response([
        _entry(1, food_usage_class="primary_ingredient"),
        _entry(2, food_usage_class="snack_or_treat"),
    ]))

    result = classify_batch(generator, ["KYLLINGFILET", "Kvikk Lunsj"])

    assert result["KYLLINGFILET"]["food_usage_class"] == "primary_ingredient"
    assert result["KYLLINGFILET"]["recipe_eligible"] is True
    assert result["Kvikk Lunsj"]["food_usage_class"] == "snack_or_treat"
    assert result["Kvikk Lunsj"]["recipe_eligible"] is False


def test_classify_batch_derives_eligibility_rather_than_trusting_the_llm_directly():
    """recipe_eligible/recipe_exclusion_reason are always computed by
    product_classification.build_classification(), never read from the LLM response
    directly -- confirming the LLM's shopping_group/food_usage_class alone determine
    the outcome regardless of anything else in the raw entry."""
    generator = _FakeGenerator(response=_classifications_response([
        _entry(1, shopping_group="non_food", food_usage_class="primary_ingredient"),
    ]))

    result = classify_batch(generator, ["FACE CONTROL CREAM"])

    assert result["FACE CONTROL CREAM"]["shopping_group"] == "non_food"
    assert result["FACE CONTROL CREAM"]["recipe_eligible"] is False
    assert result["FACE CONTROL CREAM"]["recipe_exclusion_reason"] == "non_food"


def test_classify_batch_treats_low_confidence_as_unknown():
    """A model reporting its own low confidence is Epic A's "ambiguous" case -- the
    important rule is to exclude rather than trust a guess the model itself flagged as
    unreliable, regardless of which food_usage_class it guessed."""
    generator = _FakeGenerator(response=_classifications_response([
        _entry(1, food_usage_class="primary_ingredient", confidence="low"),
    ]))

    result = classify_batch(generator, ["UKJENT VARE"])

    assert result["UKJENT VARE"]["food_usage_class"] == "unknown"
    assert result["UKJENT VARE"]["recipe_eligible"] is False
    assert result["UKJENT VARE"]["recipe_exclusion_reason"] == "insufficient_confidence"


def test_classify_batch_passes_think_false_and_a_json_schema():
    generator = _FakeGenerator(response=_classifications_response([_entry(1)]))

    classify_batch(generator, ["KYLLINGFILET"])

    _, kwargs = generator.calls[0]
    assert kwargs["think"] is False
    assert kwargs["format"]["required"] == ["classifications"]


def test_classify_batch_ignores_an_out_of_range_index():
    """A hallucinated index outside 1..len(product_names) must be dropped, not crash
    or silently misassign to the wrong product via a negative/overflowing index."""
    generator = _FakeGenerator(response=_classifications_response([_entry(1), _entry(99)]))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert set(result) == {"KYLLINGFILET"}


def test_classify_batch_ignores_an_invalid_shopping_group():
    generator = _FakeGenerator(response=json.dumps({
        "classifications": [{"index": 1, "shopping_group": "not_a_real_group", "food_usage_class": "primary_ingredient", "confidence": "high"}]
    }))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result == {}


def test_classify_batch_ignores_an_invalid_food_usage_class():
    generator = _FakeGenerator(response=json.dumps({
        "classifications": [{"index": 1, "shopping_group": "food", "food_usage_class": "not_a_real_class", "confidence": "high"}]
    }))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result == {}


def test_classify_batch_defaults_an_invalid_meal_role_to_other():
    """meal_role is the least critical field -- an invalid value shouldn't sink an
    otherwise-valid classification the way a bad shopping_group/food_usage_class does."""
    generator = _FakeGenerator(response=json.dumps({
        "classifications": [{
            "index": 1, "shopping_group": "food", "food_usage_class": "primary_ingredient",
            "meal_role": "not_a_real_role", "confidence": "high",
        }]
    }))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result["KYLLINGFILET"]["meal_role"] == "other"


def test_classify_batch_returns_empty_dict_on_malformed_json():
    generator = _FakeGenerator(response="not json at all")

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result == {}


def test_classify_batch_returns_empty_dict_when_the_llm_call_raises():
    """Ollama unreachable, timeout, whatever -- must never propagate and crash the
    cron job; the caller falls back to the keyword heuristic for this run and retries
    next time (see refresh_discounts.py)."""
    generator = _FakeGenerator(raises=ConnectionError("no route to host"))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result == {}


def test_classify_batch_omits_a_name_missing_from_the_response():
    """The LLM covering only some of the requested indices must not be treated as an
    error -- whatever it didn't return is just left unclassified."""
    generator = _FakeGenerator(response=_classifications_response([_entry(1)]))

    result = classify_batch(generator, ["KYLLINGFILET", "UKJENT VARE"])

    assert set(result) == {"KYLLINGFILET"}


def test_classify_new_products_dedupes_before_batching():
    generator = _FakeGenerator(response=_classifications_response([_entry(1)]))

    result = classify_new_products(generator, ["KYLLINGFILET", "KYLLINGFILET"], batch_size=30)

    assert set(result) == {"KYLLINGFILET"}
    assert len(generator.calls) == 1


def test_classify_new_products_splits_into_multiple_batches():
    responses = [
        _classifications_response([_entry(1), _entry(2, food_usage_class="snack_or_treat")]),
        _classifications_response([_entry(1, shopping_group="non_food")]),
    ]

    class _SequencedGenerator(_FakeGenerator):
        def chat(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return responses[len(self.calls) - 1]

    generator = _SequencedGenerator()
    result = classify_new_products(generator, ["A", "B", "C"], batch_size=2)

    assert len(generator.calls) == 2
    assert result["A"]["food_usage_class"] == "primary_ingredient"
    assert result["B"]["food_usage_class"] == "snack_or_treat"
    assert result["C"]["shopping_group"] == "non_food"

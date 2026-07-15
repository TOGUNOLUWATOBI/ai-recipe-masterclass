"""Tests for product_classifier.py -- the LLM-based classification step that upgrades
grocery_discounts.py's keyword-heuristic category for products discounts_store's
product_categories cache hasn't seen before. Uses a fake generator (no real Ollama
call) so these run offline and fast; see the module docstring for why any failure here
must degrade to "leave this product unclassified" rather than guessing or crashing."""

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


def _classifications_response(pairs):
    """pairs: list of (index, category) -- mirrors the real Ollama response shape."""
    return json.dumps({"classifications": [{"index": i, "category": c} for i, c in pairs]})


def test_build_prompt_numbers_each_product_starting_at_one():
    prompt = _build_prompt(["KYLLINGFILET", "Kvikk Lunsj"])
    assert "1. KYLLINGFILET" in prompt
    assert "2. Kvikk Lunsj" in prompt


def test_classify_batch_returns_empty_dict_for_empty_input():
    generator = _FakeGenerator()
    assert classify_batch(generator, []) == {}
    assert generator.calls == []


def test_classify_batch_maps_indices_back_to_product_names():
    generator = _FakeGenerator(response=_classifications_response([(1, "main_food"), (2, "snack")]))

    result = classify_batch(generator, ["KYLLINGFILET", "Kvikk Lunsj"])

    assert result == {"KYLLINGFILET": "main_food", "Kvikk Lunsj": "snack"}


def test_classify_batch_passes_think_false_and_a_json_schema(monkeypatch):
    generator = _FakeGenerator(response=_classifications_response([(1, "main_food")]))

    classify_batch(generator, ["KYLLINGFILET"])

    _, kwargs = generator.calls[0]
    assert kwargs["think"] is False
    assert kwargs["format"]["required"] == ["classifications"]


def test_classify_batch_ignores_an_out_of_range_index():
    """A hallucinated index outside 1..len(product_names) must be dropped, not crash
    or silently misassign to the wrong product via a negative/overflowing index."""
    generator = _FakeGenerator(response=_classifications_response([(1, "main_food"), (99, "snack")]))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result == {"KYLLINGFILET": "main_food"}


def test_classify_batch_ignores_an_invalid_category_value():
    generator = _FakeGenerator(response=json.dumps({
        "classifications": [{"index": 1, "category": "not_a_real_category"}]
    }))

    result = classify_batch(generator, ["KYLLINGFILET"])

    assert result == {}


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
    generator = _FakeGenerator(response=_classifications_response([(1, "main_food")]))

    result = classify_batch(generator, ["KYLLINGFILET", "UKJENT VARE"])

    assert result == {"KYLLINGFILET": "main_food"}
    assert "UKJENT VARE" not in result


def test_classify_new_products_dedupes_before_batching():
    generator = _FakeGenerator(response=_classifications_response([(1, "main_food")]))

    result = classify_new_products(generator, ["KYLLINGFILET", "KYLLINGFILET"], batch_size=30)

    assert result == {"KYLLINGFILET": "main_food"}
    assert len(generator.calls) == 1


def test_classify_new_products_splits_into_multiple_batches():
    responses = [
        _classifications_response([(1, "main_food"), (2, "snack")]),
        _classifications_response([(1, "non_food")]),
    ]

    class _SequencedGenerator(_FakeGenerator):
        def chat(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return responses[len(self.calls) - 1]

    generator = _SequencedGenerator()
    result = classify_new_products(generator, ["A", "B", "C"], batch_size=2)

    assert len(generator.calls) == 2
    assert result == {"A": "main_food", "B": "snack", "C": "non_food"}

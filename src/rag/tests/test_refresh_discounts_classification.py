"""Tests for refresh_discounts.py's classification pipeline -- distinct from
test_refresh_discounts.py's staleness-gate tests, which stub this step out entirely.
Covers Epic A's full processing order: manual overrides (always win) -> permanent
cache (only unseen names go further) -> the LLM classifier for whatever's left -> the
result overriding the keyword-heuristic classification already on each item."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from rag import refresh_discounts


class _FakeConfig:
    def __init__(self):
        self.DISCOUNTS_DB_PATH = "unused-in-tests.db"
        self.DISCOUNT_REFRESH_MIN_INTERVAL_HOURS = 20
        self.CATEGORY_LLM_MODEL = "qwen3:8b"
        self.OLLAMA_BASE_URL = "http://ollama:11434"
        self.OLLAMA_API_KEY = ""
        self.LLM_API_STYLE = "ollama"


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(refresh_discounts, "RecipeRAGConfig", lambda: _FakeConfig())


@pytest.fixture(autouse=True)
def _patch_tjek_client(monkeypatch):
    monkeypatch.setattr(refresh_discounts, "TjekClient", MagicMock())


@pytest.fixture(autouse=True)
def _stale_cache(monkeypatch):
    # Always take the "proceed with sweep" branch -- these tests care about the
    # classification step, not the staleness gate (see test_refresh_discounts.py).
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    monkeypatch.setattr(refresh_discounts, "get_latest_snapshot", lambda db_path: ([], old_iso))
    monkeypatch.setattr(refresh_discounts, "save_snapshot", MagicMock())


@pytest.fixture(autouse=True)
def _no_manual_overrides_by_default(monkeypatch):
    # Most tests here care about the cache/LLM split, not manual overrides --
    # test_manual_override_always_wins_and_is_re_cached below overrides this.
    monkeypatch.setattr(refresh_discounts, "load_manual_overrides", MagicMock(return_value={}))


def _classification(**overrides):
    base = {
        "shopping_group": "food",
        "food_usage_class": "primary_ingredient",
        "meal_role": "protein",
        "recipe_eligible": True,
        "recipe_exclusion_reason": None,
    }
    base.update(overrides)
    return base


def _item(name, category="main_food", recipe_eligible=True):
    return {"product_name": name, "category": category, "recipe_eligible": recipe_eligible}


def test_only_uncached_product_names_are_sent_to_the_llm(monkeypatch):
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("KYLLINGFILET"), _item("NY VARE")]),
    )
    monkeypatch.setattr(
        refresh_discounts, "get_cached_classifications",
        lambda db_path, names: {"KYLLINGFILET": _classification()},
    )
    mock_generator_cls = MagicMock()
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", mock_generator_cls)
    mock_classify = MagicMock(return_value={"NY VARE": _classification(food_usage_class="snack_or_treat", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat")})
    monkeypatch.setattr(refresh_discounts, "classify_new_products", mock_classify)
    monkeypatch.setattr(refresh_discounts, "save_classifications", MagicMock())

    refresh_discounts.main()

    mock_classify.assert_called_once()
    generator_arg, names_arg = mock_classify.call_args.args
    assert generator_arg is mock_generator_cls.return_value
    assert names_arg == ["NY VARE"]


def test_llm_classification_overrides_the_keyword_classification(monkeypatch):
    """The item's classification fields (already set by the keyword heuristic in
    find_discounted_products()) must be replaced with the LLM's answer when one is
    available -- this is the whole point of layering the LLM on top."""
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("SØRLANDSIS")]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_classifications", lambda db_path, names: {})
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    monkeypatch.setattr(
        refresh_discounts, "classify_new_products",
        MagicMock(return_value={"SØRLANDSIS": _classification(food_usage_class="snack_or_treat", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat")}),
    )
    monkeypatch.setattr(refresh_discounts, "save_classifications", MagicMock())
    mock_save_snapshot = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save_snapshot)

    refresh_discounts.main()

    saved_discounts = mock_save_snapshot.call_args.args[1]
    assert saved_discounts[0]["category"] == "snack"
    assert saved_discounts[0]["food_usage_class"] == "snack_or_treat"
    assert saved_discounts[0]["recipe_eligible"] is False


def test_items_the_llm_did_not_classify_keep_their_keyword_classification(monkeypatch):
    """A partial LLM result (e.g. only some items covered, or the call failed
    entirely) must not blank out or otherwise disturb the keyword-heuristic
    classification already present for whatever wasn't covered."""
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("UKJENT VARE")]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_classifications", lambda db_path, names: {})
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    # Simulates a failed/partial LLM call -- product_classifier.py's own contract is
    # to omit anything it couldn't classify, never guess.
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={}))
    mock_save_snapshot = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save_snapshot)

    refresh_discounts.main()

    saved_discounts = mock_save_snapshot.call_args.args[1]
    assert saved_discounts[0]["category"] == "main_food"
    assert saved_discounts[0]["recipe_eligible"] is True


def test_newly_classified_products_are_persisted_to_the_cache(monkeypatch):
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("NY VARE")]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_classifications", lambda db_path, names: {})
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    new_classification = _classification(food_usage_class="snack_or_treat", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat")
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={"NY VARE": new_classification}))
    mock_save_classifications = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_classifications", mock_save_classifications)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", MagicMock())

    refresh_discounts.main()

    mock_save_classifications.assert_called_once()
    args, kwargs = mock_save_classifications.call_args
    assert args[0] == "unused-in-tests.db"
    assert args[1] == {"NY VARE": new_classification}
    assert kwargs["classification_source"] == "llm"


def test_skips_llm_entirely_when_every_product_name_is_already_cached(monkeypatch):
    """No new names this run -- must not construct a RecipeGenerator or call the LLM
    classifier at all, since there's nothing for it to do."""
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("KYLLINGFILET")]),
    )
    monkeypatch.setattr(
        refresh_discounts, "get_cached_classifications",
        lambda db_path, names: {"KYLLINGFILET": _classification()},
    )
    mock_generator_cls = MagicMock()
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", mock_generator_cls)
    mock_classify = MagicMock()
    monkeypatch.setattr(refresh_discounts, "classify_new_products", mock_classify)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", MagicMock())

    refresh_discounts.main()

    mock_generator_cls.assert_not_called()
    mock_classify.assert_not_called()


def test_manual_override_always_wins_and_is_re_cached(monkeypatch):
    """A manual override (Epic A5) must take precedence even over what the keyword
    heuristic already set, must never be sent to the LLM, and must be re-persisted to
    the cache every run (source="manual_override") so it stays authoritative even if
    a stale LLM/heuristic result for the same name is already cached."""
    monkeypatch.setattr(
        refresh_discounts, "load_manual_overrides",
        MagicMock(return_value={"COCA-COLA ZERO": _classification(food_usage_class="beverage", meal_role="not_applicable", recipe_eligible=False, recipe_exclusion_reason="beverage")}),
    )
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("COCA-COLA ZERO", category="main_food", recipe_eligible=True)]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_classifications", lambda db_path, names: {})
    mock_generator_cls = MagicMock()
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", mock_generator_cls)
    mock_classify = MagicMock()
    monkeypatch.setattr(refresh_discounts, "classify_new_products", mock_classify)
    mock_save_classifications = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_classifications", mock_save_classifications)
    mock_save_snapshot = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save_snapshot)

    refresh_discounts.main()

    # never sent to the LLM
    mock_generator_cls.assert_not_called()
    mock_classify.assert_not_called()

    # re-cached with source="manual_override"
    override_call = next(
        call for call in mock_save_classifications.call_args_list
        if call.kwargs.get("classification_source") == "manual_override"
    )
    assert "COCA-COLA ZERO" in override_call.args[1]

    saved_discounts = mock_save_snapshot.call_args.args[1]
    assert saved_discounts[0]["category"] == "snack"
    assert saved_discounts[0]["food_usage_class"] == "beverage"
    assert saved_discounts[0]["recipe_eligible"] is False

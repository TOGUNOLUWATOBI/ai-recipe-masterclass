"""Tests for refresh_discounts.py's LLM classification integration -- distinct from
test_refresh_discounts.py's staleness-gate tests, which stub this step out entirely.
Covers the cache-first split: only product names discounts_store's product_categories
table hasn't seen before get sent to the LLM, the LLM's result overrides the
keyword-heuristic category already on each item, and a genuinely new-name-free run
skips constructing a RecipeGenerator/calling the LLM at all."""

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


def test_only_uncached_product_names_are_sent_to_the_llm(monkeypatch):
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[
            {"product_name": "KYLLINGFILET", "category": "main_food"},
            {"product_name": "NY VARE", "category": "main_food"},
        ]),
    )
    monkeypatch.setattr(
        refresh_discounts, "get_cached_categories",
        lambda db_path, names: {"KYLLINGFILET": "main_food"},
    )
    mock_generator_cls = MagicMock()
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", mock_generator_cls)
    mock_classify = MagicMock(return_value={"NY VARE": "snack"})
    monkeypatch.setattr(refresh_discounts, "classify_new_products", mock_classify)
    monkeypatch.setattr(refresh_discounts, "save_categories", MagicMock())

    refresh_discounts.main()

    mock_classify.assert_called_once()
    generator_arg, names_arg = mock_classify.call_args.args
    assert generator_arg is mock_generator_cls.return_value
    assert names_arg == ["NY VARE"]


def test_llm_classification_overrides_the_keyword_category(monkeypatch):
    """The item's category (already set by the keyword heuristic in
    find_discounted_products()) must be replaced with the LLM's answer when one is
    available -- this is the whole point of layering the LLM on top."""
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[{"product_name": "SØRLANDSIS", "category": "main_food"}]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_categories", lambda db_path, names: {})
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={"SØRLANDSIS": "snack"}))
    mock_save_snapshot = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save_snapshot)

    refresh_discounts.main()

    saved_discounts = mock_save_snapshot.call_args.args[1]
    assert saved_discounts[0]["category"] == "snack"


def test_items_the_llm_did_not_classify_keep_their_keyword_category(monkeypatch):
    """A partial LLM result (e.g. only some items covered, or the call failed
    entirely) must not blank out or otherwise disturb the keyword-heuristic category
    already present for whatever wasn't covered."""
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[{"product_name": "UKJENT VARE", "category": "main_food"}]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_categories", lambda db_path, names: {})
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    # Simulates a failed/partial LLM call -- product_classifier.py's own contract is
    # to omit anything it couldn't classify, never guess.
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={}))
    mock_save_snapshot = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save_snapshot)

    refresh_discounts.main()

    saved_discounts = mock_save_snapshot.call_args.args[1]
    assert saved_discounts[0]["category"] == "main_food"


def test_newly_classified_categories_are_persisted_to_the_cache(monkeypatch):
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[{"product_name": "NY VARE", "category": "main_food"}]),
    )
    monkeypatch.setattr(refresh_discounts, "get_cached_categories", lambda db_path, names: {})
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={"NY VARE": "snack"}))
    mock_save_categories = MagicMock()
    monkeypatch.setattr(refresh_discounts, "save_categories", mock_save_categories)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", MagicMock())

    refresh_discounts.main()

    mock_save_categories.assert_called_once_with("unused-in-tests.db", {"NY VARE": "snack"})


def test_skips_llm_entirely_when_every_product_name_is_already_cached(monkeypatch):
    """No new names this run -- must not construct a RecipeGenerator or call the LLM
    classifier at all, since there's nothing for it to do."""
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[{"product_name": "KYLLINGFILET", "category": "main_food"}]),
    )
    monkeypatch.setattr(
        refresh_discounts, "get_cached_categories",
        lambda db_path, names: {"KYLLINGFILET": "main_food"},
    )
    mock_generator_cls = MagicMock()
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", mock_generator_cls)
    mock_classify = MagicMock()
    monkeypatch.setattr(refresh_discounts, "classify_new_products", mock_classify)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", MagicMock())

    refresh_discounts.main()

    mock_generator_cls.assert_not_called()
    mock_classify.assert_not_called()

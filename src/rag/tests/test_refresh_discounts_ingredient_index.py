"""Integration test for Epic F2: refresh_discounts.py's main() must actually rebuild
the discount_ingredient_index table against a real database, not just call mocked-out
functions -- distinct from test_refresh_discounts_classification.py, which mocks
open_connection() entirely and so can't catch a wiring mistake in the real
discounts_store.rebuild_ingredient_index()/get_ingredient_index_rows() round trip."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rag import refresh_discounts
from rag.discounts_store import get_ingredient_index_rows


class _FakeConfig:
    def __init__(self, db_path):
        self.DISCOUNTS_DB_PATH = db_path
        self.DISCOUNT_REFRESH_MIN_INTERVAL_HOURS = 20
        self.CATEGORY_LLM_MODEL = "qwen3:8b"
        self.OLLAMA_BASE_URL = "http://ollama:11434"
        self.OLLAMA_API_KEY = ""
        self.LLM_API_STYLE = "ollama"


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp) / "discounts.db")


def _item(name, store_name="Kiwi", category="main_food", recipe_eligible=True):
    return {
        "product_name": name, "store_name": store_name, "category": category,
        "recipe_eligible": recipe_eligible, "current_price": 80.0, "reference_price": 100.0,
        "discount_pct": 20.0, "unit_price": 160.0, "unit_price_unit": "kg",
        "image_url": None, "store_logo_url": None,
        "valid_from": "2026-07-13T00:00:00Z", "valid_until": "2026-07-19T23:59:59Z",
        "shopping_group": "food" if recipe_eligible else "non_food",
        "food_usage_class": "primary_ingredient" if recipe_eligible else "beverage",
        "meal_role": "protein" if recipe_eligible else "not_applicable",
        "recipe_exclusion_reason": None if recipe_eligible else "beverage",
    }


def test_main_rebuilds_the_ingredient_index_against_a_real_database(db_path, monkeypatch):
    monkeypatch.setattr(refresh_discounts, "RecipeRAGConfig", lambda: _FakeConfig(db_path))
    monkeypatch.setattr(refresh_discounts, "TjekClient", MagicMock())
    monkeypatch.setattr(
        refresh_discounts, "find_discounted_products",
        MagicMock(return_value=[_item("KYLLINGFILET"), _item("COCA-COLA", recipe_eligible=False)]),
    )
    monkeypatch.setattr(refresh_discounts, "load_manual_overrides", MagicMock(return_value={}))
    # Neither item is manually overridden or already cached -- keep step 4 offline
    # rather than constructing a real RecipeGenerator/hitting a real LLM.
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={}))

    refresh_discounts.main()

    rows = get_ingredient_index_rows(db_path)

    assert len(rows) == 1
    assert rows[0]["normalized_ingredient_key"] == "chicken fillet"
    assert rows[0]["original_product_name"] == "KYLLINGFILET"


def test_main_replaces_the_previous_index_build_on_the_next_refresh(db_path, monkeypatch):
    monkeypatch.setattr(refresh_discounts, "RecipeRAGConfig", lambda: _FakeConfig(db_path))
    monkeypatch.setattr(refresh_discounts, "TjekClient", MagicMock())
    monkeypatch.setattr(refresh_discounts, "load_manual_overrides", MagicMock(return_value={}))
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={}))

    monkeypatch.setattr(refresh_discounts, "find_discounted_products", MagicMock(return_value=[_item("KYLLINGFILET")]))
    refresh_discounts.main()

    # Force the staleness gate to allow a second sweep.
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    monkeypatch.setattr(refresh_discounts, "get_latest_snapshot", lambda db_path, conn=None: ([], old_iso))
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", MagicMock(return_value=[_item("LAKSEFILET")]))
    refresh_discounts.main()

    rows = get_ingredient_index_rows(db_path)

    assert [r["normalized_ingredient_key"] for r in rows] == ["salmon fillet"]

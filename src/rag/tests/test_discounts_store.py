"""Tests for the SQLite discount cache — the read/write contract between
refresh_discounts.py (writer) and pipeline_server.py's /recipes/discounted (reader)."""

import tempfile
from pathlib import Path

import pytest

from rag.discounts_store import get_latest_snapshot, save_snapshot

_SAMPLE = [
    {
        "product_name": "Kyllingfilet 500g",
        "category": "main_food",
        "current_price": 80.0,
        "reference_price": 100.0,
        "discount_pct": 20.0,
        "unit_price": 160.0,
        "unit_price_unit": "kg",
        "image_url": "https://example.com/chicken.jpg",
        "store_name": "Kiwi",
        "store_logo_url": "https://kassal.app/logos/Kiwi.svg",
    },
    {
        "product_name": "Laksefilet 400g",
        "category": "main_food",
        "current_price": 90.0,
        "reference_price": 150.0,
        "discount_pct": 40.0,
        "unit_price": 225.0,
        "unit_price_unit": "kg",
        "image_url": "https://example.com/salmon.jpg",
        "store_name": "Meny",
        "store_logo_url": "https://kassal.app/logos/Meny.svg",
    },
]


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp) / "nested" / "discounts.db")


def test_get_latest_snapshot_returns_empty_before_any_scan(db_path):
    discounts, updated_at = get_latest_snapshot(db_path)
    assert discounts == []
    assert updated_at is None


def test_save_and_get_roundtrip(db_path):
    save_snapshot(db_path, _SAMPLE, scanned_at="2026-07-08T06:00:00+00:00")

    discounts, updated_at = get_latest_snapshot(db_path)

    assert updated_at == "2026-07-08T06:00:00+00:00"
    assert len(discounts) == 2
    assert {d["product_name"] for d in discounts} == {"Kyllingfilet 500g", "Laksefilet 400g"}
    salmon = next(d for d in discounts if d["product_name"] == "Laksefilet 400g")
    assert salmon["store_name"] == "Meny"
    assert salmon["discount_pct"] == 40.0
    assert salmon["category"] == "main_food"


def test_save_snapshot_orders_by_discount_pct_descending(db_path):
    save_snapshot(db_path, _SAMPLE, scanned_at="2026-07-08T06:00:00+00:00")

    discounts, _ = get_latest_snapshot(db_path)

    assert [d["product_name"] for d in discounts] == ["Laksefilet 400g", "Kyllingfilet 500g"]


def test_save_snapshot_replaces_previous_scan_entirely(db_path):
    save_snapshot(db_path, _SAMPLE, scanned_at="2026-07-01T06:00:00+00:00")
    save_snapshot(db_path, [_SAMPLE[0]], scanned_at="2026-07-08T06:00:00+00:00")

    discounts, updated_at = get_latest_snapshot(db_path)

    assert updated_at == "2026-07-08T06:00:00+00:00"
    assert len(discounts) == 1
    assert discounts[0]["product_name"] == "Kyllingfilet 500g"


def test_save_snapshot_with_no_discounts_still_records_scan_time():
    """A scan that legitimately finds nothing on sale must still update scan_meta —
    otherwise "scanned, nothing on sale right now" is indistinguishable from "the cron
    job has never run" to the API/UI."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "discounts.db")
        save_snapshot(db_path, [], scanned_at="2026-07-08T06:00:00+00:00")

        discounts, updated_at = get_latest_snapshot(db_path)

        assert discounts == []
        assert updated_at == "2026-07-08T06:00:00+00:00"


def test_save_and_get_roundtrip_preserves_none_discount_fields(db_path):
    """Regression test: the backend now returns every product per store, not just
    confirmed discounts (see grocery_discounts.py) -- discount_pct/reference_price are
    None for most rows now, and this must round-trip as real None, not get coerced to
    0/0.0 by SQLite, and must not break the DESC ordering (a None discount_pct must
    sort after real ones, not crash or sort first)."""
    plain_item = {
        "product_name": "Cola 0,5l",
        "current_price": 20.0,
        "reference_price": None,
        "discount_pct": None,
        "unit_price": None,
        "unit_price_unit": None,
        "image_url": None,
        "store_name": "Kiwi",
        "store_logo_url": None,
    }
    save_snapshot(db_path, _SAMPLE + [plain_item], scanned_at="2026-07-08T06:00:00+00:00")

    discounts, _ = get_latest_snapshot(db_path)

    assert len(discounts) == 3
    plain_result = next(d for d in discounts if d["product_name"] == "Cola 0,5l")
    assert plain_result["discount_pct"] is None
    assert plain_result["reference_price"] is None
    # discounted items (highest first) must still sort ahead of the undiscounted one
    assert [d["product_name"] for d in discounts][-1] == "Cola 0,5l"


def test_get_latest_snapshot_creates_parent_directory_if_missing(db_path):
    assert not Path(db_path).parent.exists()

    get_latest_snapshot(db_path)

    assert Path(db_path).parent.exists()


def test_save_snapshot_migrates_a_pre_category_database(db_path):
    """Every deployed DB predates the `category` column -- simulate one (table created
    without it, like a real pre-migration file) and confirm a save/read cycle against it
    adds the column instead of crashing with "no such column"."""
    import sqlite3

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE discounts (
            scanned_at TEXT NOT NULL,
            product_name TEXT,
            current_price REAL,
            reference_price REAL,
            discount_pct REAL,
            unit_price REAL,
            unit_price_unit TEXT,
            image_url TEXT,
            store_name TEXT,
            store_logo_url TEXT
        )
    """)
    conn.execute("CREATE TABLE scan_meta (id INTEGER PRIMARY KEY CHECK (id = 0), last_scanned_at TEXT NOT NULL)")
    conn.commit()
    conn.close()

    save_snapshot(db_path, _SAMPLE, scanned_at="2026-07-15T06:00:00+00:00")
    discounts, updated_at = get_latest_snapshot(db_path)

    assert updated_at == "2026-07-15T06:00:00+00:00"
    salmon = next(d for d in discounts if d["product_name"] == "Laksefilet 400g")
    assert salmon["category"] == "main_food"

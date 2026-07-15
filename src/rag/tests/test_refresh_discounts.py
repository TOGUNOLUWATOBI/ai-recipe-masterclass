"""Tests for refresh_discounts.py's self-healing staleness gate. Standard cron doesn't
retry a missed fixed-time firing (e.g. the host asleep/offline at 5am) -- confirmed live:
the cache silently sat 3 days stale with nothing surfacing the problem. main() now checks
the cached snapshot's age before doing a full Tjek sweep and skips it when the snapshot is
still fresh, so pairing this with a more frequent cron (hourly) lets any wake-up catch up
automatically instead of waiting up to 24h for the next exact firing."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from rag import refresh_discounts


class _FakeConfig:
    """Stand-in for RecipeRAGConfig with just the fields main() reads, so tests can
    fix DISCOUNT_REFRESH_MIN_INTERVAL_HOURS without depending on its real default.
    CATEGORY_LLM_MODEL/OLLAMA_*/LLM_API_STYLE are only ever read inside the
    `if uncached_names:` branch, which _patch_classification's mocked
    get_cached_categories (returns {}, so nothing is ever "already cached") combined
    with a mocked RecipeGenerator keeps from making any real call -- present here only
    so that branch doesn't AttributeError before reaching the mocks."""

    def __init__(self, min_interval_hours=20):
        self.DISCOUNTS_DB_PATH = "unused-in-tests.db"
        self.DISCOUNT_REFRESH_MIN_INTERVAL_HOURS = min_interval_hours
        self.CATEGORY_LLM_MODEL = "qwen3:8b"
        self.OLLAMA_BASE_URL = "http://ollama:11434"
        self.OLLAMA_API_KEY = ""
        self.LLM_API_STYLE = "ollama"


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(refresh_discounts, "RecipeRAGConfig", lambda: _FakeConfig())


@pytest.fixture(autouse=True)
def _patch_tjek_client(monkeypatch):
    # TjekClient() must never actually be constructed/hit the network in these tests --
    # find_discounted_products is mocked directly regardless of what it's called with.
    monkeypatch.setattr(refresh_discounts, "TjekClient", MagicMock())


@pytest.fixture(autouse=True)
def _patch_classification(monkeypatch):
    # The LLM classification step (product_classifier.py) is a separate concern from
    # the staleness gate this file otherwise tests -- default it to a no-op (nothing
    # cached, nothing newly classified) so these tests never construct a real
    # RecipeGenerator or hit a real network. test_refresh_discounts_classification.py
    # overrides these to test the integration itself.
    monkeypatch.setattr(refresh_discounts, "get_cached_categories", MagicMock(return_value={}))
    monkeypatch.setattr(refresh_discounts, "save_categories", MagicMock())
    monkeypatch.setattr(refresh_discounts, "RecipeGenerator", MagicMock())
    monkeypatch.setattr(refresh_discounts, "classify_new_products", MagicMock(return_value={}))


def _iso(age: timedelta) -> str:
    return (datetime.now(timezone.utc) - age).isoformat()


def test_fresh_snapshot_skips_the_sweep(monkeypatch):
    """A snapshot well within the min-interval window (e.g. a healthy daily cron's cache,
    only a couple hours old) must skip the sweep entirely -- no Tjek calls, no cache
    overwrite."""
    monkeypatch.setattr(
        refresh_discounts, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "OLD"}], _iso(timedelta(hours=2))),
    )
    mock_find = MagicMock()
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()

    mock_find.assert_not_called()
    mock_save.assert_not_called()


def test_stale_snapshot_proceeds_with_the_sweep(monkeypatch):
    """A snapshot older than the min-interval (e.g. the machine was asleep for days, as
    confirmed live) must trigger a full sweep exactly like today, refreshing the cache."""
    monkeypatch.setattr(
        refresh_discounts, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "OLD"}], _iso(timedelta(hours=72))),
    )
    mock_find = MagicMock(return_value=[{"product_name": "NEW", "discount_pct": 10.0}])
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()

    mock_find.assert_called_once()
    mock_save.assert_called_once()
    assert mock_save.call_args.args[1] == [{"product_name": "NEW", "discount_pct": 10.0}]


def test_no_snapshot_yet_proceeds_with_the_sweep(monkeypatch):
    """First-ever run (cache never populated, get_latest_snapshot returns ([], None))
    must not be treated as "fresh" -- there's nothing to compare an age against, so the
    sweep must proceed."""
    monkeypatch.setattr(refresh_discounts, "get_latest_snapshot", lambda db_path: ([], None))
    mock_find = MagicMock(return_value=[])
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()

    mock_find.assert_called_once()
    mock_save.assert_called_once()


def test_snapshot_exactly_at_threshold_proceeds_with_the_sweep(monkeypatch):
    """Boundary condition: a snapshot exactly DISCOUNT_REFRESH_MIN_INTERVAL_HOURS old is
    no longer "younger than" the threshold, so it should not be considered fresh -- the
    sweep proceeds rather than skipping. (Age computed from a fixed instant is always
    monotonically >= the nominal boundary once wall-clock time has elapsed since building
    the fixture string, so this also guards against an off-by-one flipping the comparison
    direction.)"""
    monkeypatch.setattr(
        refresh_discounts, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "OLD"}], _iso(timedelta(hours=20))),
    )
    mock_find = MagicMock(return_value=[])
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()

    mock_find.assert_called_once()
    mock_save.assert_called_once()


def test_snapshot_just_under_threshold_skips_the_sweep(monkeypatch):
    """Complements the exactly-at-threshold case: a snapshot a few seconds *younger* than
    the threshold must still be treated as fresh and skip."""
    monkeypatch.setattr(
        refresh_discounts, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "OLD"}], _iso(timedelta(hours=20) - timedelta(seconds=30))),
    )
    mock_find = MagicMock()
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()

    mock_find.assert_not_called()
    mock_save.assert_not_called()


def test_naive_timestamp_is_treated_as_utc(monkeypatch):
    """Defensive: scanned_at is always produced via datetime.now(timezone.utc).isoformat()
    today (an offset-aware string), but the parsing must not blow up with a "can't
    subtract offset-naive and offset-aware datetimes" TypeError if a naive ISO string
    ever shows up (e.g. hand-edited cache, older format) -- it should be interpreted as
    UTC rather than crash the cron job."""
    naive_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None).isoformat()
    monkeypatch.setattr(
        refresh_discounts, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "OLD"}], naive_iso),
    )
    mock_find = MagicMock()
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()

    mock_find.assert_not_called()
    mock_save.assert_not_called()


def test_malformed_timestamp_falls_through_to_the_sweep(monkeypatch):
    """A corrupt/unparseable scanned_at (bad manual edit, format change, etc.) must not
    crash the whole cron job with an uncaught ValueError -- that would turn every
    subsequent hourly invocation into an identical crash loop, defeating the entire
    point of this self-healing gate. It should be treated the same as "no valid
    snapshot" and proceed with a fresh sweep."""
    monkeypatch.setattr(
        refresh_discounts, "get_latest_snapshot",
        lambda db_path: ([{"product_name": "OLD"}], "not-a-real-timestamp"),
    )
    mock_find = MagicMock(return_value=[{"product_name": "NEW"}])
    mock_save = MagicMock()
    monkeypatch.setattr(refresh_discounts, "find_discounted_products", mock_find)
    monkeypatch.setattr(refresh_discounts, "save_snapshot", mock_save)

    refresh_discounts.main()  # must not raise

    mock_find.assert_called_once()
    mock_save.assert_called_once()

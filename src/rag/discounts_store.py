"""SQLite-backed cache for the grocery discount scan. The underlying flyer offers
refresh roughly weekly (like any Norwegian "kundeavis"), not per-request — so having
/recipes/discounted run a live scan on every hit would be needless load for data
that's already stale by the next request. A scheduled job (refresh_discounts.py, run
via cron — see deployment notes) is the only writer; the API (pipeline_server.py) only
ever reads the latest snapshot here.

Deliberately a plain relational table, not a JSON blob: every discounted-ingredient
record already shares the same fixed set of fields (see grocery_discounts.py), so there's
no schema flexibility to buy by giving that up.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS discounts (
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
);
CREATE TABLE IF NOT EXISTS scan_meta (
    id INTEGER PRIMARY KEY CHECK (id = 0),
    last_scanned_at TEXT NOT NULL
);
"""

_COLUMNS = [
    "product_name", "current_price", "reference_price",
    "discount_pct", "unit_price", "unit_price_unit", "image_url", "store_name", "store_logo_url",
]


@contextmanager
def _connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_snapshot(db_path: str, discounts: List[Dict[str, Any]], scanned_at: str) -> None:
    """Replaces the entire cache with one new snapshot tagged with a single scanned_at
    shared by every row — old snapshots are dropped, not accumulated, since only the
    latest is ever served. scan_meta is updated even when discounts is empty (nothing
    currently on sale), so that state stays distinguishable from "never scanned"."""
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM discounts")
        if discounts:
            conn.executemany(
                f"""INSERT INTO discounts (scanned_at, {", ".join(_COLUMNS)})
                    VALUES (:scanned_at, {", ".join(f":{c}" for c in _COLUMNS)})""",
                [{**{c: d.get(c) for c in _COLUMNS}, "scanned_at": scanned_at} for d in discounts],
            )
        conn.execute(
            """INSERT INTO scan_meta (id, last_scanned_at) VALUES (0, ?)
               ON CONFLICT(id) DO UPDATE SET last_scanned_at = excluded.last_scanned_at""",
            (scanned_at,),
        )


def get_latest_snapshot(db_path: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Returns (discounts, scanned_at) — ([], None) if the cache has never been
    populated (e.g. before the first cron run has ever fired)."""
    with _connect(db_path) as conn:
        meta = conn.execute("SELECT last_scanned_at FROM scan_meta WHERE id = 0").fetchone()
        if meta is None:
            return [], None
        rows = conn.execute("SELECT * FROM discounts ORDER BY discount_pct DESC").fetchall()

    discounts = [{c: row[c] for c in _COLUMNS} for row in rows]
    return discounts, meta["last_scanned_at"]

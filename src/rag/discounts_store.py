"""SQLite-backed cache for the grocery discount scan. The underlying flyer offers
refresh roughly weekly (like any Norwegian "kundeavis"), not per-request — so having
/recipes/discounted run a live scan on every hit would be needless load for data
that's already stale by the next request. A scheduled job (refresh_discounts.py, run
via cron — see deployment notes) is the only writer; the API (pipeline_server.py) only
ever reads the latest snapshot here.

Deliberately a plain relational table, not a JSON blob: every discounted-ingredient
record already shares the same fixed set of fields (see grocery_discounts.py), so there's
no schema flexibility to buy by giving that up.

Also holds `product_categories`, a *separate*, never-wiped table (unlike `discounts`,
which save_snapshot() replaces wholesale every scan) — a permanent product_name ->
category cache so a product classified once (via the LLM classifier in
product_classifier.py, see refresh_discounts.py) is never re-sent to the LLM again,
even after it drops out of one scan and reappears in a later one.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS discounts (
    scanned_at TEXT NOT NULL,
    product_name TEXT,
    category TEXT,
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
CREATE TABLE IF NOT EXISTS product_categories (
    product_name TEXT PRIMARY KEY,
    category TEXT NOT NULL
);
"""

_COLUMNS = [
    "product_name", "category", "current_price", "reference_price",
    "discount_pct", "unit_price", "unit_price_unit", "image_url", "store_name", "store_logo_url",
]


@contextmanager
def _connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        # CREATE TABLE IF NOT EXISTS above is a no-op against a discounts table that
        # already existed pre-`category` (every deployed DB before this field was
        # added) -- add the column by hand for those, since SQLite has no
        # ADD COLUMN IF NOT EXISTS.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(discounts)")}
        if "category" not in existing_columns:
            conn.execute("ALTER TABLE discounts ADD COLUMN category TEXT")
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


def get_cached_categories(db_path: str, product_names: List[str]) -> Dict[str, str]:
    """Returns whichever of the given product names already have a cached category --
    a name absent from the returned dict has never been classified before (by the LLM
    classifier or otherwise) and needs a fresh classification."""
    if not product_names:
        return {}
    with _connect(db_path) as conn:
        placeholders = ", ".join("?" for _ in product_names)
        rows = conn.execute(
            f"SELECT product_name, category FROM product_categories WHERE product_name IN ({placeholders})",
            product_names,
        ).fetchall()
    return {row["product_name"]: row["category"] for row in rows}


def save_categories(db_path: str, categories: Dict[str, str]) -> None:
    """Upserts newly-classified product_name -> category pairs. Never deletes existing
    entries -- this table accumulates indefinitely, unlike `discounts` (see module
    docstring), so a product already classified is never reclassified even if it
    temporarily drops out of the current scan."""
    if not categories:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            """INSERT INTO product_categories (product_name, category) VALUES (?, ?)
               ON CONFLICT(product_name) DO UPDATE SET category = excluded.category""",
            list(categories.items()),
        )

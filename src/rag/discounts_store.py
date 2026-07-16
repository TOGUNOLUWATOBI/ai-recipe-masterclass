"""SQLite-backed cache for the grocery discount scan. The underlying flyer offers
refresh roughly weekly (like any Norwegian "kundeavis"), not per-request — so having
/recipes/discounted run a live scan on every hit would be needless load for data
that's already stale by the next request. A scheduled job (refresh_discounts.py, run
via cron — see deployment notes) is the only writer; the API (pipeline_server.py) only
ever reads the latest snapshot here.

Deliberately a plain relational table, not a JSON blob: every discounted-ingredient
record already shares the same fixed set of fields (see grocery_discounts.py), so there's
no schema flexibility to buy by giving that up.

Also holds `product_classifications` (Epic A), a *separate*, never-wiped table (unlike
`discounts`, which save_snapshot() replaces wholesale every scan) — a permanent
product_name -> full classification cache (shopping_group, food_usage_class,
meal_role, recipe_eligible, recipe_exclusion_reason, plus classification_source/
confidence/classified_at/classifier_version for auditing -- see Epic J's "most
frequently corrected products") so a product classified once (via the keyword
heuristic, the LLM classifier, or a manual override -- see product_classification.py
and product_classifier.py) is never re-sent to the LLM again, even after it drops out
of one scan and reappears in a later one. This replaces the older, flatter
`product_categories` table (product_name -> a single "main_food"/"snack"/"non_food"
string) -- new deployments only get the richer table; an existing DB's old
product_categories table, if present, is simply left unused rather than migrated,
since every row in it gets naturally re-derived (heuristic first, LLM second) the
next time that product name shows up in a scan.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .product_classification import ProductClassification

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
CREATE TABLE IF NOT EXISTS product_classifications (
    product_name TEXT PRIMARY KEY,
    shopping_group TEXT NOT NULL,
    food_usage_class TEXT NOT NULL,
    meal_role TEXT NOT NULL,
    recipe_eligible INTEGER NOT NULL,
    recipe_exclusion_reason TEXT,
    classification_source TEXT NOT NULL,
    classification_confidence TEXT,
    classified_at TEXT NOT NULL,
    classifier_version TEXT NOT NULL
);
"""

# Legacy label kept for backward compatibility with the mobile app's existing
# Food/Non-food tab split -- see product_classification.legacy_category(). The
# columns after it are Epic A's richer classification, added to an existing
# `discounts` table via ALTER TABLE below since CREATE TABLE IF NOT EXISTS is a
# no-op against a table that predates them (every DB deployed before Epic A).
_COLUMNS = [
    "product_name", "category",
    "shopping_group", "food_usage_class", "meal_role", "recipe_eligible", "recipe_exclusion_reason",
    "current_price", "reference_price",
    "discount_pct", "unit_price", "unit_price_unit", "image_url", "store_name", "store_logo_url",
]

# Columns that predate Epic A -- anything in _COLUMNS but not here gets added via
# ALTER TABLE for a pre-existing `discounts` table missing it. SQLite has no
# ADD COLUMN IF NOT EXISTS, hence the manual PRAGMA table_info check below.
_LEGACY_COLUMNS = {
    "product_name", "category", "current_price", "reference_price", "discount_pct",
    "unit_price", "unit_price_unit", "image_url", "store_name", "store_logo_url",
}

_NEW_DISCOUNT_COLUMN_TYPES = {
    "shopping_group": "TEXT",
    "food_usage_class": "TEXT",
    "meal_role": "TEXT",
    "recipe_eligible": "INTEGER",
    "recipe_exclusion_reason": "TEXT",
}


@contextmanager
def _connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        # CREATE TABLE IF NOT EXISTS above is a no-op against a discounts table that
        # already existed pre-`category`/pre-Epic A (every DB deployed before each of
        # these fields was added) -- add whichever columns are missing by hand, since
        # SQLite has no ADD COLUMN IF NOT EXISTS.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(discounts)")}
        if "category" not in existing_columns:
            conn.execute("ALTER TABLE discounts ADD COLUMN category TEXT")
            existing_columns.add("category")
        for column, sql_type in _NEW_DISCOUNT_COLUMN_TYPES.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE discounts ADD COLUMN {column} {sql_type}")
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
    populated (e.g. before the first cron run has ever fired). `recipe_eligible` is
    coerced back to a real bool (SQLite has no native boolean type -- it's stored as
    0/1) for every row that has it; rows written before Epic A existed have it as
    None, which coerces to False, matching classify_product()'s old "no field means
    don't feed this into recipe generation" absence semantics being replaced anyway
    the next time refresh_discounts.py reclassifies that row."""
    with _connect(db_path) as conn:
        meta = conn.execute("SELECT last_scanned_at FROM scan_meta WHERE id = 0").fetchone()
        if meta is None:
            return [], None
        rows = conn.execute("SELECT * FROM discounts ORDER BY discount_pct DESC").fetchall()

    discounts = []
    for row in rows:
        item = {c: row[c] for c in _COLUMNS}
        item["recipe_eligible"] = bool(item["recipe_eligible"])
        discounts.append(item)
    return discounts, meta["last_scanned_at"]


def get_cached_classifications(db_path: str, product_names: List[str]) -> Dict[str, ProductClassification]:
    """Returns whichever of the given product names already have a cached
    classification -- a name absent from the returned dict has never been classified
    before (by the LLM classifier or otherwise) and needs a fresh classification."""
    if not product_names:
        return {}
    with _connect(db_path) as conn:
        placeholders = ", ".join("?" for _ in product_names)
        rows = conn.execute(
            f"""SELECT product_name, shopping_group, food_usage_class, meal_role,
                       recipe_eligible, recipe_exclusion_reason
                FROM product_classifications WHERE product_name IN ({placeholders})""",
            product_names,
        ).fetchall()
    return {
        row["product_name"]: {
            "shopping_group": row["shopping_group"],
            "food_usage_class": row["food_usage_class"],
            "meal_role": row["meal_role"],
            "recipe_eligible": bool(row["recipe_eligible"]),
            "recipe_exclusion_reason": row["recipe_exclusion_reason"],
        }
        for row in rows
    }


def save_classifications(
    db_path: str,
    classifications: Dict[str, ProductClassification],
    classification_source: str,
    classified_at: str,
    classifier_version: str,
    classification_confidence: Optional[str] = None,
) -> None:
    """Upserts newly-classified product_name -> ProductClassification pairs, all
    sharing one classification_source/classified_at/classifier_version/confidence
    (callers batch by source -- see refresh_discounts.py, which calls this once for
    the LLM batch and once for manual overrides). Never deletes existing entries --
    this table accumulates indefinitely, unlike `discounts` (see module docstring),
    so a product already classified is never reclassified even if it temporarily
    drops out of the current scan."""
    if not classifications:
        return
    with _connect(db_path) as conn:
        conn.executemany(
            """INSERT INTO product_classifications
                   (product_name, shopping_group, food_usage_class, meal_role,
                    recipe_eligible, recipe_exclusion_reason, classification_source,
                    classification_confidence, classified_at, classifier_version)
               VALUES (:product_name, :shopping_group, :food_usage_class, :meal_role,
                       :recipe_eligible, :recipe_exclusion_reason, :classification_source,
                       :classification_confidence, :classified_at, :classifier_version)
               ON CONFLICT(product_name) DO UPDATE SET
                   shopping_group = excluded.shopping_group,
                   food_usage_class = excluded.food_usage_class,
                   meal_role = excluded.meal_role,
                   recipe_eligible = excluded.recipe_eligible,
                   recipe_exclusion_reason = excluded.recipe_exclusion_reason,
                   classification_source = excluded.classification_source,
                   classification_confidence = excluded.classification_confidence,
                   classified_at = excluded.classified_at,
                   classifier_version = excluded.classifier_version""",
            [
                {
                    "product_name": name,
                    "shopping_group": c["shopping_group"],
                    "food_usage_class": c["food_usage_class"],
                    "meal_role": c["meal_role"],
                    "recipe_eligible": int(c["recipe_eligible"]),
                    "recipe_exclusion_reason": c["recipe_exclusion_reason"],
                    "classification_source": classification_source,
                    "classification_confidence": classification_confidence,
                    "classified_at": classified_at,
                    "classifier_version": classifier_version,
                }
                for name, c in classifications.items()
            ],
        )

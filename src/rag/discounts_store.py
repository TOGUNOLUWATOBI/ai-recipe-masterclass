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

import json
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
    store_logo_url TEXT,
    valid_from TEXT,
    valid_until TEXT
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
CREATE TABLE IF NOT EXISTS discount_ingredient_index (
    normalized_ingredient_key TEXT NOT NULL,
    ingredient_aliases TEXT,
    original_product_name TEXT NOT NULL,
    store_name TEXT,
    current_price REAL,
    reference_price REAL,
    discount_pct REAL,
    unit_price REAL,
    unit_price_unit TEXT,
    image_url TEXT,
    store_logo_url TEXT,
    valid_from TEXT,
    valid_until TEXT,
    shopping_group TEXT,
    food_usage_class TEXT,
    meal_role TEXT,
    recipe_eligible INTEGER,
    snapshot_id TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingredient_index_key ON discount_ingredient_index(normalized_ingredient_key);
CREATE TABLE IF NOT EXISTS meal_idea_feedback (
    request_id TEXT NOT NULL,
    recommendation_type TEXT NOT NULL,
    idea_title TEXT,
    helpful INTEGER NOT NULL,
    reasons TEXT,
    selected_items_used TEXT,
    missing_required_ingredients TEXT,
    source_type TEXT,
    submitted_at TEXT NOT NULL
);
"""

# Epic F1's discount_ingredient_index columns, in insert/select order.
_INGREDIENT_INDEX_COLUMNS = [
    "normalized_ingredient_key", "ingredient_aliases", "original_product_name", "store_name",
    "current_price", "reference_price", "discount_pct", "unit_price", "unit_price_unit",
    "image_url", "store_logo_url", "valid_from", "valid_until",
    "shopping_group", "food_usage_class", "meal_role", "recipe_eligible",
    "snapshot_id", "updated_at",
]

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
    # Epic F1: the flyer's own real validity window (grocery_discounts.py's
    # valid_from/valid_until) -- without these here, they only ever reached
    # discount_ingredient_index, never the main snapshot every other reader of this
    # module actually uses.
    "valid_from", "valid_until",
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
    "valid_from": "TEXT",
    "valid_until": "TEXT",
}


@contextmanager
def _connect(db_path: str, conn: Optional[sqlite3.Connection] = None):
    """Opens (and schema-initializes) a connection to db_path, or reuses `conn` if the
    caller already has one open -- see open_connection() below, used by
    refresh_discounts.py's main() to make several of the calls in this module share one
    connection instead of re-paying the schema-init PRAGMA/ALTER checks per call.

    A reused connection is deliberately NOT committed here -- every call sharing one
    connection is part of the same transaction, committed exactly once by the original
    opener's own _connect() call when its `with open_connection(...)` block exits (see
    below). Committing per-call here would let a mid-run failure (e.g. the ingredient
    index rebuild succeeding but the snapshot save failing right after) leave the
    database in a partially-updated state instead of rolling the whole run back."""
    if conn is not None:
        yield conn
        return
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


@contextmanager
def open_connection(db_path: str):
    """Opens one schema-initialized connection for a caller (e.g. refresh_discounts.py's
    main()) that makes several of this module's calls in one run -- pass the yielded
    connection as each call's `conn=` to skip re-opening the file and re-running the
    PRAGMA table_info/ALTER TABLE checks every time. Also makes the whole run atomic:
    every write made through this connection is one single transaction, committed once
    when this `with` block exits normally -- if any call raises, nothing written during
    the run is committed (e.g. a mid-refresh failure can never leave the ingredient
    index rebuilt from the new scan while the snapshot itself still reflects the old
    one)."""
    with _connect(db_path) as conn:
        yield conn


def save_snapshot(
    db_path: str, discounts: List[Dict[str, Any]], scanned_at: str,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Replaces the entire cache with one new snapshot tagged with a single scanned_at
    shared by every row — old snapshots are dropped, not accumulated, since only the
    latest is ever served. scan_meta is updated even when discounts is empty (nothing
    currently on sale), so that state stays distinguishable from "never scanned".

    Pass `conn` (see open_connection()) to reuse an already-open connection instead of
    opening a new one."""
    with _connect(db_path, conn) as c:
        c.execute("DELETE FROM discounts")
        if discounts:
            c.executemany(
                f"""INSERT INTO discounts (scanned_at, {", ".join(_COLUMNS)})
                    VALUES (:scanned_at, {", ".join(f":{c}" for c in _COLUMNS)})""",
                [{**{c: d.get(c) for c in _COLUMNS}, "scanned_at": scanned_at} for d in discounts],
            )
        c.execute(
            """INSERT INTO scan_meta (id, last_scanned_at) VALUES (0, ?)
               ON CONFLICT(id) DO UPDATE SET last_scanned_at = excluded.last_scanned_at""",
            (scanned_at,),
        )


def get_latest_snapshot(
    db_path: str, conn: Optional[sqlite3.Connection] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Returns (discounts, scanned_at) — ([], None) if the cache has never been
    populated (e.g. before the first cron run has ever fired). `recipe_eligible` is
    coerced back to a real bool (SQLite has no native boolean type -- it's stored as
    0/1) for every row that has it; rows written before Epic A existed have it as
    None, which coerces to False, matching classify_product()'s old "no field means
    don't feed this into recipe generation" absence semantics being replaced anyway
    the next time refresh_discounts.py reclassifies that row.

    Pass `conn` (see open_connection()) to reuse an already-open connection instead of
    opening a new one."""
    with _connect(db_path, conn) as c:
        meta = c.execute("SELECT last_scanned_at FROM scan_meta WHERE id = 0").fetchone()
        if meta is None:
            return [], None
        rows = c.execute("SELECT * FROM discounts ORDER BY discount_pct DESC").fetchall()

    discounts = []
    for row in rows:
        item = {c: row[c] for c in _COLUMNS}
        item["recipe_eligible"] = bool(item["recipe_eligible"])
        discounts.append(item)
    return discounts, meta["last_scanned_at"]


def get_cached_classifications(
    db_path: str, product_names: List[str], conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, ProductClassification]:
    """Returns whichever of the given product names already have a cached
    classification -- a name absent from the returned dict has never been classified
    before (by the LLM classifier or otherwise) and needs a fresh classification.

    Pass `conn` (see open_connection()) to reuse an already-open connection instead of
    opening a new one."""
    if not product_names:
        return {}
    with _connect(db_path, conn) as c:
        placeholders = ", ".join("?" for _ in product_names)
        rows = c.execute(
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


def get_classification_sources(
    db_path: str, product_names: List[str], conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, str]:
    """Epic J2: product_name -> classification_source ("llm" / "manual_override") for
    whichever of the given names have a cached row -- a name absent from the returned
    dict was never cached at all, meaning it was classified by the inline keyword
    heuristic alone (see refresh_discounts.py's step 2, which never writes to
    product_classifications since there's nothing worth caching for a cheap
    deterministic rule). classification_report.py relies on that absence to mean
    "heuristic" rather than querying for it directly."""
    if not product_names:
        return {}
    with _connect(db_path, conn) as c:
        placeholders = ", ".join("?" for _ in product_names)
        rows = c.execute(
            f"""SELECT product_name, classification_source
                FROM product_classifications WHERE product_name IN ({placeholders})""",
            product_names,
        ).fetchall()
    return {row["product_name"]: row["classification_source"] for row in rows}


def save_classifications(
    db_path: str,
    classifications: Dict[str, ProductClassification],
    classification_source: str,
    classified_at: str,
    classifier_version: str,
    classification_confidence: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Upserts newly-classified product_name -> ProductClassification pairs, all
    sharing one classification_source/classified_at/classifier_version/confidence
    (callers batch by source -- see refresh_discounts.py, which calls this once for
    the LLM batch and once for manual overrides). Never deletes existing entries --
    this table accumulates indefinitely, unlike `discounts` (see module docstring),
    so a product already classified is never reclassified even if it temporarily
    drops out of the current scan.

    Pass `conn` (see open_connection()) to reuse an already-open connection instead of
    opening a new one."""
    if not classifications:
        return
    with _connect(db_path, conn) as c:
        c.executemany(
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


def rebuild_ingredient_index(
    db_path: str, rows: List[Dict[str, Any]], conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Epic F2: replaces the entire index with one fresh build, same wholesale-replace
    pattern as save_snapshot() -- built once per discount refresh (see
    ingredient_index.build_ingredient_index_rows(), called from refresh_discounts.py
    right after classification finishes and right before the new snapshot is saved),
    never incrementally patched. `rows` is already exactly the row shape this table
    expects (see _INGREDIENT_INDEX_COLUMNS) -- this function only persists it.

    Pass `conn` (see open_connection()) to reuse an already-open connection instead of
    opening a new one."""
    with _connect(db_path, conn) as c:
        c.execute("DELETE FROM discount_ingredient_index")
        if rows:
            c.executemany(
                f"""INSERT INTO discount_ingredient_index ({", ".join(_INGREDIENT_INDEX_COLUMNS)})
                    VALUES ({", ".join(f":{col}" for col in _INGREDIENT_INDEX_COLUMNS)})""",
                [{col: row.get(col) for col in _INGREDIENT_INDEX_COLUMNS} for row in rows],
            )


def get_ingredient_index_rows(db_path: str, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Epic F3: returns the entire current index -- deliberately not filtered by
    ingredient name in SQL. The index is small (bounded by how many recipe_eligible
    products one scan finds, at most ~1400 rows -- see grocery_discounts.py), and alias/
    fuzzy matching (ingredient_index.match_ingredient_offers()) needs to compare a
    query name against every row's aliases anyway, so a single full read plus in-Python
    matching is simpler than hand-rolling that logic in SQL, and is the same "small
    dataset, match in Python" pattern the rest of this codebase already uses (see
    meal_ideas.py). Never triggers a live Tjek scan or reclassification -- purely a
    read of whatever rebuild_ingredient_index() last wrote.

    Pass `conn` (see open_connection()) to reuse an already-open connection instead of
    opening a new one."""
    with _connect(db_path, conn) as c:
        rows = c.execute(f"SELECT {', '.join(_INGREDIENT_INDEX_COLUMNS)} FROM discount_ingredient_index").fetchall()
    results = [{col: row[col] for col in _INGREDIENT_INDEX_COLUMNS} for row in rows]
    for item in results:
        # SQLite has no native boolean -- stored as 0/1/NULL, coerced back to a real
        # bool here the same way get_latest_snapshot() already does for this exact
        # field on the sibling `discounts` table, so a caller can safely use it in a
        # boolean context (e.g. `offer["recipe_eligible"] is True`).
        item["recipe_eligible"] = bool(item["recipe_eligible"])
    return results


def save_meal_idea_feedback(
    db_path: str,
    *,
    request_id: str,
    recommendation_type: str,
    idea_title: Optional[str],
    helpful: bool,
    reasons: List[str],
    selected_items_used: List[str],
    missing_required_ingredients: List[str],
    source_type: Optional[str],
    submitted_at: str,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Epic J3: one row per "Helpful"/"Not helpful" tap, storing the feedback alongside
    the specific idea's own output (title, what it used, what it was missing, whether
    it was retrieved or generated) -- never re-fetched or joined against a separate
    events store, so a feedback row stays meaningful even after the log line that
    originally reported this request has rotated out of whatever log retention this
    deployment has. `request_id` still lets it be correlated back to that original
    Epic J1 log line (recommendation_type/selected/eligible/excluded product ids,
    latency, etc.) when deeper debugging is needed. Never a hard failure path -- there's
    nothing here worth blocking the user's cart/meal-idea flow over."""
    with _connect(db_path, conn) as c:
        c.execute(
            """INSERT INTO meal_idea_feedback
                (request_id, recommendation_type, idea_title, helpful, reasons,
                 selected_items_used, missing_required_ingredients, source_type, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request_id, recommendation_type, idea_title, int(helpful), json.dumps(reasons),
                json.dumps(selected_items_used), json.dumps(missing_required_ingredients),
                source_type, submitted_at,
            ),
        )

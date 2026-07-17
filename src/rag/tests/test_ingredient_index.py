"""Tests for ingredient_index.py -- Epic F's precomputed ingredient -> offer index."""

from rag.ingredient_index import (
    build_ingredient_aliases,
    build_ingredient_index_rows,
    match_ingredient_offers,
)


def _discount(product_name, store_name="Kiwi", recipe_eligible=True, **overrides):
    row = {
        "product_name": product_name,
        "store_name": store_name,
        "current_price": 80.0,
        "reference_price": 100.0,
        "discount_pct": 20.0,
        "unit_price": 160.0,
        "unit_price_unit": "kg",
        "image_url": "https://example.com/x.jpg",
        "store_logo_url": "https://example.com/logo.svg",
        "valid_from": "2026-07-13T00:00:00Z",
        "valid_until": "2026-07-19T23:59:59Z",
        "shopping_group": "food",
        "food_usage_class": "primary_ingredient",
        "meal_role": "protein",
        "recipe_eligible": recipe_eligible,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# build_ingredient_aliases
# ---------------------------------------------------------------------------

def test_build_ingredient_aliases_adds_the_plural_form():
    assert build_ingredient_aliases("chicken fillet") == ["chicken fillet", "chicken fillets"]


def test_build_ingredient_aliases_adds_the_singular_form():
    assert build_ingredient_aliases("potatoes") == ["potato", "potatoes"]


def test_build_ingredient_aliases_does_not_mangle_a_word_already_ending_in_double_s():
    assert build_ingredient_aliases("swiss") == ["swiss"]


def test_build_ingredient_aliases_only_pluralizes_the_last_word_of_a_multi_word_name():
    assert build_ingredient_aliases("canned tomatoes") == ["canned tomato", "canned tomatoes"]


def test_build_ingredient_aliases_is_empty_for_an_empty_name():
    assert build_ingredient_aliases("") == []


def test_build_ingredient_aliases_does_not_produce_an_empty_string_alias():
    """A canonical key ending in a bare 's' must not singularize to '' -- an empty
    alias would spuriously match any query that also normalizes to an empty string."""
    assert "" not in build_ingredient_aliases("s")


def test_build_ingredient_aliases_leaves_invariant_nouns_unchanged():
    """asparagus/hummus/species etc. are already both singular and plural -- the
    ordinary pluralize/singularize rules would otherwise mangle them into a nonsense
    word (e.g. "hummus" -> "hummu")."""
    assert build_ingredient_aliases("asparagus") == ["asparagus"]
    assert build_ingredient_aliases("hummus") == ["hummus"]
    assert build_ingredient_aliases("species") == ["species"]


# ---------------------------------------------------------------------------
# build_ingredient_index_rows
# ---------------------------------------------------------------------------

def test_build_ingredient_index_rows_excludes_ineligible_products():
    """Task F1/F2: never index a beverage/snack/non-food/ready-meal product -- an
    ingredient lookup must never surface one as a recipe ingredient offer."""
    discounts = [
        _discount("KYLLINGFILET"),
        _discount("COCA-COLA", recipe_eligible=False),
    ]

    rows = build_ingredient_index_rows(discounts, snapshot_id="2026-07-16T06:00:00Z", updated_at="2026-07-16T06:00:00Z")

    assert len(rows) == 1
    assert rows[0]["original_product_name"] == "KYLLINGFILET"


def test_build_ingredient_index_rows_keys_by_the_normalized_english_name():
    discounts = [_discount("KYLLINGFILET")]

    rows = build_ingredient_index_rows(discounts, snapshot_id="s1", updated_at="2026-07-16T06:00:00Z")

    assert rows[0]["normalized_ingredient_key"] == "chicken fillet"
    assert "chicken fillet" in rows[0]["ingredient_aliases"]


def test_build_ingredient_index_rows_carries_through_the_validity_window_and_snapshot_id():
    discounts = [_discount("KYLLINGFILET", valid_from="2026-07-13T00:00:00Z", valid_until="2026-07-19T23:59:59Z")]

    rows = build_ingredient_index_rows(discounts, snapshot_id="snap-1", updated_at="2026-07-16T06:00:00Z")

    assert rows[0]["valid_from"] == "2026-07-13T00:00:00Z"
    assert rows[0]["valid_until"] == "2026-07-19T23:59:59Z"
    assert rows[0]["snapshot_id"] == "snap-1"


def test_build_ingredient_index_rows_skips_a_product_with_no_name():
    """original_product_name is NOT NULL in the schema -- a discount item with no real
    name must be skipped rather than crash the whole refresh on insert."""
    discounts = [_discount("KYLLINGFILET"), _discount(None)]

    rows = build_ingredient_index_rows(discounts, snapshot_id="s1", updated_at="2026-07-16T06:00:00Z")

    assert len(rows) == 1
    assert rows[0]["original_product_name"] == "KYLLINGFILET"


# ---------------------------------------------------------------------------
# match_ingredient_offers
# ---------------------------------------------------------------------------

def _index_row(key, aliases=None, **overrides):
    import json
    row = {
        "normalized_ingredient_key": key,
        "ingredient_aliases": json.dumps(aliases if aliases is not None else [key]),
        "original_product_name": key.upper(),
        "store_name": "Kiwi",
        "current_price": 80.0,
        "unit_price": 160.0,
        "unit_price_unit": "kg",
        "discount_pct": 20.0,
        "reference_price": 100.0,
        "image_url": None,
        "store_logo_url": None,
        "valid_from": None,
        "valid_until": None,
    }
    row.update(overrides)
    return row


def test_match_ingredient_offers_finds_an_exact_key_match():
    rows = [_index_row("chicken fillet")]

    matches = match_ingredient_offers("chicken fillet", rows)

    assert len(matches) == 1
    assert matches[0]["match_confidence"] == "exact"


def test_match_ingredient_offers_returns_ingredient_aliases_as_a_real_list():
    """A caller of /ingredient-offers should never have to JSON.parse a field it
    already received inside a JSON response -- the stored JSON-encoded column must be
    decoded before being returned, not passed through as a raw string."""
    rows = [_index_row("chicken fillet", aliases=["chicken fillet", "chicken fillets"])]

    matches = match_ingredient_offers("chicken fillet", rows)

    assert matches[0]["ingredient_aliases"] == ["chicken fillet", "chicken fillets"]


def test_match_ingredient_offers_tolerates_malformed_alias_json():
    """A single row with corrupted ingredient_aliases (hand-edited DB, a future writer
    bypassing json.dumps()) must not crash the whole request -- just treat that row as
    having no aliases and keep matching the rest."""
    rows = [
        _index_row("chicken fillet", aliases=None),  # placeholder, overwritten below
        _index_row("salmon fillet", aliases=["salmon fillet", "salmon fillets"]),
    ]
    rows[0]["ingredient_aliases"] = "not valid json"

    matches = match_ingredient_offers("salmon fillets", rows)

    assert len(matches) == 1
    assert matches[0]["original_product_name"] == "SALMON FILLET"


def test_match_ingredient_offers_finds_an_alias_match_for_the_plural_form():
    rows = [_index_row("chicken fillet", aliases=["chicken fillet", "chicken fillets"])]

    matches = match_ingredient_offers("chicken fillets", rows)

    assert len(matches) == 1
    assert matches[0]["match_confidence"] == "alias"


def test_match_ingredient_offers_finds_a_fuzzy_match_via_shared_words():
    rows = [_index_row("chicken breast fillet", aliases=["chicken breast fillet"])]

    matches = match_ingredient_offers("boneless chicken breast", rows)

    assert len(matches) == 1
    assert matches[0]["match_confidence"] == "fuzzy"


def test_match_ingredient_offers_suppresses_an_unrelated_product():
    """Task F7's hard requirement: no match beats a wrong one."""
    rows = [_index_row("lettuce")]

    matches = match_ingredient_offers("chicken fillet", rows)

    assert matches == []


def test_match_ingredient_offers_returns_empty_offers_when_nothing_matches():
    matches = match_ingredient_offers("chicken fillet", [])
    assert matches == []


def test_match_ingredient_offers_ranks_exact_above_alias_above_fuzzy():
    rows = [
        # Jaccard overlap vs "chicken fillets": {chicken, fillets} / {diced, chicken,
        # fillets} = 2/3 -- a genuine fuzzy match (an extra qualifier word), not two
        # different cuts sharing only one generic word.
        _index_row("diced chicken fillets", aliases=["diced chicken fillet", "diced chicken fillets"]),
        _index_row("chicken fillet", aliases=["chicken fillet", "chicken fillets"]),  # alias via plural query
    ]
    # add an exact-key row too
    rows.append(_index_row("chicken fillets", aliases=["chicken fillets"]))

    matches = match_ingredient_offers("chicken fillets", rows)

    assert matches[0]["match_confidence"] == "exact"
    assert matches[1]["match_confidence"] == "alias"
    assert matches[2]["match_confidence"] == "fuzzy"


def test_match_ingredient_offers_ranks_by_unit_price_ascending_within_a_tier():
    rows = [
        _index_row("chicken fillet", store_name="Meny", unit_price=200.0),
        _index_row("chicken fillet", store_name="Kiwi", unit_price=150.0),
    ]

    matches = match_ingredient_offers("chicken fillet", rows)

    assert [m["store_name"] for m in matches] == ["Kiwi", "Meny"]


def test_match_ingredient_offers_puts_a_missing_unit_price_last():
    rows = [
        _index_row("chicken fillet", store_name="NoUnitPrice", unit_price=None),
        _index_row("chicken fillet", store_name="Kiwi", unit_price=150.0),
    ]

    matches = match_ingredient_offers("chicken fillet", rows)

    assert [m["store_name"] for m in matches] == ["Kiwi", "NoUnitPrice"]


def test_match_ingredient_offers_caps_at_max_offers():
    rows = [_index_row("chicken fillet", store_name=f"Store{i}", unit_price=float(i)) for i in range(5)]

    matches = match_ingredient_offers("chicken fillet", rows, max_offers=2)

    assert len(matches) == 2
    assert [m["store_name"] for m in matches] == ["Store0", "Store1"]

"""Epic F: a precomputed ingredient -> current-offer index. discounts_store.
rebuild_ingredient_index() replaces the whole table once per discount refresh (see
refresh_discounts.py's main()), so match_ingredient_offers() below is always a fast
in-memory lookup over already-classified, already-cached data -- never a live Tjek
scan, a reclassification pass, or an LLM call (Task F3's hard requirement: opening a
recipe must never risk the model inventing a price, a store, or a product)."""

import json
import re
from typing import Any, Dict, List

from .grocery_terms import normalize_grocery_heading

_STOPWORDS = {"a", "an", "the", "of", "with", "and", "or", "to", "in", "for", "fresh"}


def _significant_words(name: str) -> List[str]:
    words = re.findall(r"[a-zA-Z]+", name.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _canonical_key(product_name: str) -> str:
    return normalize_grocery_heading(product_name or "").strip().lower()


def _pluralize(word: str) -> str:
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if word.endswith("o") and not word.endswith(("oo", "eo")):
        return word + "es"
    if len(word) > 1 and word.endswith("y") and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def _singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes", "oes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def build_ingredient_aliases(canonical_name: str) -> List[str]:
    """Task F1's alias mechanism. normalize_grocery_heading() already does the hard
    part of turning a Norwegian flyer heading into a clean canonical English name (see
    its own docstring/GROCERY_GLOSSARY for the exact "kyllingfilet" -> "chicken
    breast" / "laksefilet" -> "salmon fillet" / "poteter" -> "potato" aliasing this
    epic's story calls out) -- so the only gap left here is a recipe ingredient line
    written in the other grammatical number than the canonical key (only the last word
    is pluralized/singularized, e.g. "chicken fillet" <-> "chicken fillets", matching
    how these canonical names are actually shaped). A broader synonym dictionary is
    future work, not needed to satisfy Epic F's acceptance criteria."""
    name = canonical_name.strip().lower()
    if not name:
        return []
    prefix, _, last_word = name.rpartition(" ")
    prefix = f"{prefix} " if prefix else ""
    # Only generate the one alternate form the current word actually needs -- pluralizing
    # an already-plural word (or singularizing an already-singular one) would otherwise
    # add a nonsensical "double plural" alias (e.g. "potatoes" -> "potatoeses").
    other_form = _singularize(last_word) if last_word.endswith("s") else _pluralize(last_word)
    aliases = {name, f"{prefix}{other_form}"}
    return sorted(aliases)


def build_ingredient_index_rows(
    discounts: List[Dict[str, Any]], snapshot_id: str, updated_at: str,
) -> List[Dict[str, Any]]:
    """Task F1/F2: one row per recipe_eligible discount item (Epic A's classification --
    never an ineligible product, the same gate as everywhere else recipe-facing reads
    the snapshot), keyed by its normalized canonical name. Built from the same in-memory
    `discounts` list refresh_discounts.py has just finished classifying, right before
    save_snapshot() stamps it -- see that module's main() for the exact step ordering
    (snapshot -> classify -> normalize eligible items -> build this index -> save)."""
    rows = []
    for d in discounts:
        if not d.get("recipe_eligible"):
            continue
        canonical = _canonical_key(d.get("product_name") or "")
        rows.append({
            "normalized_ingredient_key": canonical,
            "ingredient_aliases": json.dumps(build_ingredient_aliases(canonical)),
            "original_product_name": d.get("product_name"),
            "store_name": d.get("store_name"),
            "current_price": d.get("current_price"),
            "reference_price": d.get("reference_price"),
            "discount_pct": d.get("discount_pct"),
            "unit_price": d.get("unit_price"),
            "unit_price_unit": d.get("unit_price_unit"),
            "image_url": d.get("image_url"),
            "store_logo_url": d.get("store_logo_url"),
            "valid_from": d.get("valid_from"),
            "valid_until": d.get("valid_until"),
            "shopping_group": d.get("shopping_group"),
            "food_usage_class": d.get("food_usage_class"),
            "meal_role": d.get("meal_role"),
            "recipe_eligible": d.get("recipe_eligible"),
            "snapshot_id": snapshot_id,
            "updated_at": updated_at,
        })
    return rows


# Task F7: a fuzzy match needs at least half the query ingredient's significant words
# to show up in a candidate row's own key -- deliberately conservative ("the app would
# rather show no match than a wrong product").
_MIN_FUZZY_WORD_OVERLAP_RATIO = 0.5


def _by_unit_price(offer: Dict[str, Any]) -> tuple:
    """Task F6: rank by comparable unit price, cheapest first -- a row with no
    unit_price (couldn't be computed, see grocery_discounts._compute_unit_price())
    sorts after every row that has one rather than crashing on a None comparison."""
    unit_price = offer.get("unit_price")
    return (unit_price is None, unit_price if unit_price is not None else 0.0)


def match_ingredient_offers(
    ingredient_name: str, index_rows: List[Dict[str, Any]], max_offers: int = 5,
) -> List[Dict[str, Any]]:
    """Task F3/F7: normalize -> exact key match -> alias match -> fuzzy (shared
    significant-word overlap) fallback, in that priority order. Every returned offer is
    tagged with its own match_confidence ("exact"/"alias"/"fuzzy") so a caller can hide
    or visibly label a low-confidence fuzzy match instead of presenting it with the
    same trust as a real one.

    `index_rows` is expected to already be the full current index (see
    discounts_store.get_ingredient_index_rows()) -- this function only matches
    in-memory, never queries anything live, so lookup cost never depends on how large
    the ingredient catalogue grows.

    Within each confidence tier, results are ranked by unit price ascending (Task F6)
    before being capped at max_offers -- a short, genuinely comparable list rather than
    every offer that happens to match."""
    target = _canonical_key(ingredient_name)
    target_words = set(_significant_words(target))

    exact: List[Dict[str, Any]] = []
    alias: List[Dict[str, Any]] = []
    fuzzy: List[Dict[str, Any]] = []

    for row in index_rows:
        key = row.get("normalized_ingredient_key") or ""
        if key == target:
            exact.append({**row, "match_confidence": "exact"})
            continue

        row_aliases = json.loads(row.get("ingredient_aliases") or "[]")
        if target in row_aliases:
            alias.append({**row, "match_confidence": "alias"})
            continue

        row_words = set(_significant_words(key))
        if not target_words or not row_words:
            continue
        overlap_ratio = len(target_words & row_words) / len(target_words)
        if overlap_ratio >= _MIN_FUZZY_WORD_OVERLAP_RATIO:
            fuzzy.append({**row, "match_confidence": "fuzzy"})

    ranked = sorted(exact, key=_by_unit_price) + sorted(alias, key=_by_unit_price) + sorted(fuzzy, key=_by_unit_price)
    return ranked[:max_offers]

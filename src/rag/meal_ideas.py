"""Epic C: generates practical meal ideas from a selection of cart products, corpus-first
with an LLM-generation fallback -- the backend half of POST /meal-ideas/from-cart.

The mobile cart has no durable per-offer ID from the backend to key off of (see
mobile-app/src/types/cart.ts's cartItemIdFor()), so `discount_item_ids` in the request
are exactly the same `f"{store_name}::{product_name}"` strings the app already
generates -- this module recomputes the identical key server-side (_discount_item_id())
to resolve them against the current discount snapshot, rather than trusting whatever
classification/eligibility the client claims (Task C1's "do not trust client-provided
classifications").

Pipeline (mirrors Task C1-C8 in order):
  1. resolve_cart_items() -- match requested ids against the latest cached snapshot.
     Anything that doesn't resolve (an id for an offer that's disappeared from the
     cache entirely) is excluded with reason "not_found".
  2. filter_eligible_items() -- keep only recipe_eligible rows (Epic A's classification,
     already computed at refresh time); everything else is excluded with its own
     recipe_exclusion_reason. This is what guarantees Coca-Cola/frozen pizza/laundry
     detergent can never reach a retrieval query, an LLM prompt, or a returned recipe's
     title/ingredient list/explanation (Task C2's hard requirement).
  3. Normalize + dedupe the eligible product names (grocery_terms.normalize_grocery_heading,
     the same unconditional normalization /recipes/discounted already applies -- cart
     items are always Tjek-sourced, never arbitrary user text).
  4. Retrieve corpus candidates first (pipeline.find_recipes_from_ingredients) --
     generation is only used as a fallback when retrieval returns nothing usable
     (Task C3).
  5. Split each candidate's ingredient lines into required/optional (Epic D's
     recipe_structuring.structure_ingredients()) and score coverage deterministically
     against the required set only (Task C4) -- never left to the LLM's judgment, and
     never counting an optional garnish or an assumed pantry basic (salt/water/oil)
     against a recipe's completion status.
  6. Rank by completion tier, then coverage, then simplicity (Task C5 -- the corpus has
     no explicit complexity/cooking-time field, so required-ingredient count is the
     best available proxy for "simpler"; a real complexity/time signal is future work
     once that data exists).
  7. Every idea reports only the subset of eligible ingredients it actually used --
     nothing here ever tries to force all selected products into one dish (Task C6).

estimated_complexity and servings are always null -- neither the corpus nor generation
currently produces that data; a real signal for either is future work, not something
this module fabricates. Epic G (the shared, cross-endpoint AI behavior policy with
few-shot examples and full response validation) is also a separate, later epic -- the
system prompt and temperature below are this endpoint's own minimal, working version of
that policy (now folding in Task D4's tone rules too), expected to be refactored into
Epic G's shared module once it lands.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .grocery_terms import normalize_grocery_heading
from .pipeline import RecipeRAGPipeline, _parse_recipe_sections
from .recipe_structuring import structure_ingredients

logger = logging.getLogger(__name__)

# Epic C4 completion-status thresholds -- deliberately simple constants (not yet
# user-configurable) rather than magic numbers scattered through the module; easy to
# expose via config.py later if that turns out to matter.
_NEARLY_COMPLETE_MAX_MISSING = 2

# Retrieved pool size before ranking/truncating to max_results -- wider than
# max_results so a real match ranked lower by raw retrieval score can still surface
# once coverage-based ranking (Task C5) re-sorts the pool.
_CANDIDATE_POOL_SIZE = 15

_STOPWORDS = {"a", "an", "the", "of", "with", "and", "or", "to", "in", "for", "fresh"}


def _discount_item_id(row: Dict[str, Any]) -> str:
    """Same (store_name, product_name) key convention as the mobile app's
    cartItemIdFor() -- see that function's docstring for why this approximation (no
    real per-offer id exists yet) is good enough: unique within one discount scan,
    which is all either side ever needs it for."""
    return f"{row.get('store_name') or 'unknown-store'}::{row.get('product_name')}"


def resolve_cart_items(
    discount_item_ids: List[str], discounts: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Matches requested ids against the latest cached snapshot. Returns
    (resolved_rows, excluded_entries) -- an id with no matching row (the offer expired
    out of the cache, or the client sent a stale/malformed id) is never a hard error,
    just an excluded entry the caller still gets to see (Epic C7's excluded_cart_items,
    useful for debugging even though the app doesn't have to show it prominently)."""
    by_id = {_discount_item_id(row): row for row in discounts}
    resolved: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for item_id in discount_item_ids:
        row = by_id.get(item_id)
        if row is None:
            excluded.append({"product_name": item_id, "reason": "not_found"})
        else:
            resolved.append(row)
    return resolved, excluded


def filter_eligible_items(
    resolved_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keeps only recipe_eligible rows (Epic A's classification, already computed at
    discount-refresh time -- never re-derived here, and never trusting anything the
    client itself might claim about a product). Everything else is excluded with its
    own recipe_exclusion_reason so the caller can distinguish *why* (non_food,
    beverage, finished_meal, snack_or_treat, insufficient_confidence) rather than a
    single opaque "excluded" bucket."""
    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for row in resolved_rows:
        if row.get("recipe_eligible"):
            eligible.append(row)
        else:
            excluded.append({
                "product_name": row.get("product_name"),
                "reason": row.get("recipe_exclusion_reason") or "other",
            })
    return eligible, excluded


def normalize_and_dedupe(eligible_rows: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Returns [(original_product_name, normalized_name), ...], deduped by normalized
    name (case-insensitive) -- Task C2's "deduplicate equivalent ingredients", e.g. two
    different stores both discounting "KYLLINGFILET" should only count as one
    ingredient, not two. First-seen original name wins for a given normalized name."""
    seen: Dict[str, str] = {}
    result: List[Tuple[str, str]] = []
    for row in eligible_rows:
        original = row.get("product_name") or ""
        normalized = normalize_grocery_heading(original)
        key = normalized.strip().lower()
        if key in seen:
            continue
        seen[key] = original
        result.append((original, normalized))
    return result


def _significant_words(name: str) -> List[str]:
    words = re.findall(r"[a-zA-Z]+", name.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _ingredient_line_matches(line: str, normalized_cart_name: str) -> bool:
    """Deliberately simple heuristic: a recipe ingredient line counts as covered by a
    cart ingredient if ANY of the cart ingredient's significant words appears as a
    whole word (allowing a plural/suffix continuation, e.g. "chop" matching "chops")
    in the line. No stemming beyond that, no synonym awareness beyond whatever
    normalize_grocery_heading() already provides. This is intentionally a v1 -- good
    enough to separate "ground beef" matching "1 lb ground beef" from not matching
    "2 carrots", without a full NLP ingredient parser that doesn't exist in this
    codebase. A more precise matcher is future work, not a blocker for Epic C."""
    words = _significant_words(normalized_cart_name)
    if not words:
        return False
    line_lower = line.lower()
    return any(re.search(rf"\b{re.escape(word)}\w*\b", line_lower) for word in words)


def compute_coverage(
    required_ingredient_names: List[str], normalized_cart_names: List[str]
) -> Dict[str, Any]:
    """Deterministic ingredient-coverage matching (Task C4) -- never left to the LLM's
    judgment. Takes clean ingredient *names* (Epic D's recipe_structuring.
    structure_ingredients() output, quantity already stripped, optional/pantry-basic
    lines already excluded) rather than raw lines -- coverage and completion_status are
    about the required set specifically, so an optional garnish or an assumed pantry
    basic (salt/water/oil) never counts as "missing" against a recipe."""
    matched_cart_names: List[str] = []
    missing_names: List[str] = []

    for name in required_ingredient_names:
        matched_name = next(
            (cart_name for cart_name in normalized_cart_names if _ingredient_line_matches(name, cart_name)), None
        )
        if matched_name is not None:
            if matched_name not in matched_cart_names:
                matched_cart_names.append(matched_name)
        else:
            missing_names.append(name)

    total = len(required_ingredient_names)
    coverage_pct = round(100 * (total - len(missing_names)) / total, 1) if total else 0.0
    return {
        "matched_cart_names": matched_cart_names,
        "missing_required_ingredients": missing_names,
        "ingredient_coverage_percentage": coverage_pct,
    }


def completion_status(total_ingredients: int, missing_count: int) -> str:
    """Task C4's three-tier status. complete/nearly_complete/partial thresholds are
    plain module constants for now (see _NEARLY_COMPLETE_MAX_MISSING) rather than
    exposed config -- easy to promote later if tuning turns out to matter."""
    if total_ingredients == 0 or missing_count == 0:
        return "complete"
    if missing_count <= _NEARLY_COMPLETE_MAX_MISSING:
        return "nearly_complete"
    return "partial"


def _rank_key(idea: Dict[str, Any]) -> Tuple[int, float, int, int]:
    """Task C5: everyday/simple meals rank above elaborate ones. Sorted ascending, so
    lower is better -- completion tier first (complete=0 beats partial=2), then
    coverage percentage (negated, since higher coverage should sort first), then
    number of cart ingredients actually used (negated, more used is better among
    equal-coverage ties), then total recipe ingredient count (fewer ingredients is the
    best available "simpler/more everyday" proxy given the corpus has no explicit
    complexity or cooking-time field -- see module docstring)."""
    tier = {"complete": 0, "nearly_complete": 1, "partial": 2}[idea["completion_status"]]
    return (
        tier,
        -idea["ingredient_coverage_percentage"],
        -len(idea["selected_items_used"]),
        len(idea["required_ingredients"]),
    )


def _build_idea_from_corpus_result(
    result: Dict[str, Any], normalized_cart_names: List[str]
) -> Optional[Dict[str, Any]]:
    """Builds one structured idea (Task C7, now enriched by Epic D's required/optional
    split) from a single retrieved corpus recipe. Returns None if the recipe doesn't
    actually use any of the cart's ingredients -- coverage matching can occasionally
    retrieve something related-but-not-really-a-match (BM25/dense similarity isn't the
    same claim as "uses this ingredient"), and a zero-match "idea" isn't a meaningful
    cart-based suggestion."""
    payload = result.get("payload") or {}
    raw_ingredients: List[str] = payload.get("ingredients") or []
    structured = structure_ingredients(raw_ingredients)
    required = structured["required_ingredients"]
    optional = structured["optional_ingredients"]

    required_names = [ing["name"] for ing in required]
    coverage = compute_coverage(required_names, normalized_cart_names)
    if not coverage["matched_cart_names"]:
        return None

    missing = coverage["missing_required_ingredients"]
    return {
        "title": payload.get("title"),
        "description": None,
        "servings": None,
        "completion_status": completion_status(len(required), len(missing)),
        "selected_items_used": coverage["matched_cart_names"],
        "required_ingredients": required,
        "optional_ingredients": optional,
        "missing_required_ingredients": missing,
        "ingredient_coverage_percentage": coverage["ingredient_coverage_percentage"],
        "pantry_basics_assumed": structured["pantry_basics_assumed"],
        "estimated_complexity": None,
        "source_type": "retrieved",
    }


# Epic G's shared, tested everyday-meal policy (few-shot examples, response
# validation, tuned temperature) doesn't exist yet -- this is this endpoint's own
# minimal working version of that policy (see module docstring), covering just what
# Task C2/C5/C6 need: use only what's listed, never force every ingredient into one
# dish, keep it ordinary rather than restaurant-style.
_MEAL_IDEAS_SYSTEM_PROMPT = """You are an everyday home-cooking assistant helping someone plan a meal from groceries they already have.

STRICT RULES:
1. Suggest a practical, familiar meal an ordinary home cook would actually make -- never a restaurant-style, deconstructed, or unusually creative dish.
2. You do not have to use every ingredient listed -- use whichever subset makes one sensible, coherent meal, and ignore the rest.
3. Never invent an ingredient that isn't listed and isn't a basic pantry staple (salt, water, cooking oil, pepper).
4. Present the ingredients you actually use as a simple, clean bulleted list, and the steps as a numbered list.
5. Keep instructions short and plain: about 4 to 8 steps, ordinary short sentences, no professional culinary terms, no plating direction, and never describe the dish as "gourmet", "elevated", or "restaurant-quality".
6. Use only standard, plain English text. Never use R-programming syntax (like c(), quotes, or brackets around lists).
7. Do not include conversational filler."""

# Three distinct angles for three separate calls -- asking one call for "3 meal ideas"
# doesn't work (confirmed empirically elsewhere in this codebase, see
# pipeline.find_recipes_or_generate(): the fine-tuned model always returns exactly one
# recipe regardless of the instruction). Phrased to actively encourage using only a
# subset (Task C6) rather than reaching for every ingredient at once.
_GENERATION_ANGLES = [
    "Suggest one simple, everyday meal using some or all of these ingredients: {ing}. It's fine to use only some of them if that makes for a more sensible dish.",
    "Suggest a different simple, everyday meal using some or all of these ingredients: {ing}.",
    "Suggest a quick, ordinary weeknight meal using some or all of these ingredients: {ing}.",
]

_INGREDIENT_LINE_RE = re.compile(r"^\s*[-*•]\s*(.+)$")


def _split_generated_ingredient_lines(ingredients_block: str) -> List[str]:
    """Splits a generated recipe's already-extracted **Ingredients:** block into
    individual lines -- reliable here (unlike the corpus's comma-joined text, see
    recipe_loader.py) because the system prompt above explicitly requires a bulleted
    list and the fine-tuned model has already been confirmed to follow that
    convention (see pipeline.py's SYSTEM_PROMPT and _parse_recipe_sections())."""
    lines = []
    for raw_line in ingredients_block.splitlines():
        match = _INGREDIENT_LINE_RE.match(raw_line)
        text = match.group(1) if match else raw_line.strip()
        if text:
            lines.append(text)
    return lines


def _generate_fallback_ideas(
    pipeline: RecipeRAGPipeline, normalized_cart_names: List[str], max_results: int
) -> List[Dict[str, Any]]:
    """Task C3's fallback path -- only reached when retrieval returns nothing usable.
    Mirrors find_recipes_or_generate()'s "one angle per call" mechanism (see that
    function's own comment for why: OpenWebUI silently pins temperature, native Ollama
    doesn't) but with a meal-ideas-specific system prompt/temperature (Task G3's
    spirit: lower variance than the general multi-recipe-suggestion flow, since the
    goal here is a sensible everyday meal, not maximally diverse options)."""
    ingredients_str = ", ".join(normalized_cart_names)
    n = min(max_results, len(_GENERATION_ANGLES))
    ideas: List[Dict[str, Any]] = []

    for i in range(n):
        prompt = _GENERATION_ANGLES[i].format(ing=ingredients_str)
        try:
            answer = pipeline.generator.generate(
                prompt, "(no matching reference recipe found)", _MEAL_IDEAS_SYSTEM_PROMPT,
                options={"temperature": 0.5},
            )
        except Exception as e:
            logger.error(f"Meal-idea generation angle {i + 1}/{n} failed: {e}")
            continue

        sections = _parse_recipe_sections(answer)
        ingredients_block = sections.get("ingredients")
        if not ingredients_block:
            continue
        raw_ingredients = _split_generated_ingredient_lines(ingredients_block)
        structured = structure_ingredients(raw_ingredients)
        required = structured["required_ingredients"]
        optional = structured["optional_ingredients"]

        required_names = [ing["name"] for ing in required]
        coverage = compute_coverage(required_names, normalized_cart_names)
        if not coverage["matched_cart_names"]:
            continue

        missing = coverage["missing_required_ingredients"]
        ideas.append({
            "title": sections.get("title"),
            "description": None,
            "servings": None,
            "completion_status": completion_status(len(required), len(missing)),
            "selected_items_used": coverage["matched_cart_names"],
            "required_ingredients": required,
            "optional_ingredients": optional,
            "missing_required_ingredients": missing,
            "ingredient_coverage_percentage": coverage["ingredient_coverage_percentage"],
            "pantry_basics_assumed": structured["pantry_basics_assumed"],
            "estimated_complexity": None,
            "source_type": "generated",
        })

    return ideas


def generate_meal_ideas_from_cart(
    pipeline: RecipeRAGPipeline,
    discounts: List[Dict[str, Any]],
    discount_item_ids: List[str],
    max_results: int = 5,
    language: str = "en",
) -> Dict[str, Any]:
    """Orchestrates the full Task C1-C8 pipeline -- see module docstring for the
    numbered steps. `language` is accepted for API-shape consistency with the rest of
    pipeline_server.py's endpoints but not yet applied here -- meal ideas aren't
    translated to Norwegian in this first version (Epic C's own acceptance criteria
    don't require it); wiring it through translator.py the same way
    find_recipes_or_generate() does is straightforward follow-up work once needed."""
    resolved_rows, not_found = resolve_cart_items(discount_item_ids, discounts)
    eligible_rows, ineligible = filter_eligible_items(resolved_rows)
    excluded_cart_items = not_found + ineligible

    # Task C8: zero eligible ingredients -- never call retrieval/generation with an
    # empty query, just report what got excluded and why.
    if not eligible_rows:
        return {"ideas": [], "excluded_cart_items": excluded_cart_items}

    name_pairs = normalize_and_dedupe(eligible_rows)
    normalized_cart_names = [normalized for _, normalized in name_pairs]

    grounded = pipeline.find_recipes_from_ingredients(
        normalized_cart_names, max_results=_CANDIDATE_POOL_SIZE, normalize=False,
    )

    ideas = []
    for result in grounded:
        idea = _build_idea_from_corpus_result(result, normalized_cart_names)
        if idea is not None:
            ideas.append(idea)

    source_type = "retrieved"
    if not ideas:
        # Task C3: generation is the fallback, only reached when retrieval produced
        # nothing usable.
        ideas = _generate_fallback_ideas(pipeline, normalized_cart_names, max_results)
        source_type = "generated"

    ideas.sort(key=_rank_key)
    return {
        "ideas": ideas[:max_results],
        "excluded_cart_items": excluded_cart_items,
        # Not part of Task C7's documented response shape, but a cheap, useful signal
        # for the app/logs to know which branch produced these ideas without having to
        # inspect every individual idea's own source_type.
        "source": source_type if ideas else None,
    }

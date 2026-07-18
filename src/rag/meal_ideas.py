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
this module fabricates. Epic G's shared everyday-meal policy (system prompt, few-shot
examples, temperature, response validation) lives in ai_policy.py and is applied by
_generate_fallback_ideas() below.

Epic J1: both entry points log one structured recommendation_event (see
observability.py) after the pipeline finishes -- request tracing/quality
monitoring, never anything a client needs to see, so it's a side effect around the
edges of each entry point rather than something threaded through the return value.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .ai_policy import GENERATION_TEMPERATURE, build_meal_ideas_system_prompt, validate_generated_idea
from .grocery_terms import normalize_grocery_heading
from .observability import log_recommendation_event, new_request_id
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


def resolve_store_items(store_name: str, discounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Epic E (Task E2/E3): every cached row for one store, from the same snapshot
    get_latest_snapshot() already returned -- a plain in-memory filter, never a new
    Tjek scan, reclassification, or discount re-analysis (Task E2's hard rule). No
    separate precomputed per-store table is needed for this: every row already carries
    its own meal_role/recipe_eligible from refresh time (Epic A), so filtering the
    existing snapshot by store_name at request time is exactly as cheap as reading a
    dedicated one would be, without a second structure to keep in sync."""
    return [row for row in discounts if (row.get("store_name") or "unknown-store") == store_name]


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


def _generate_one_idea(
    pipeline: RecipeRAGPipeline, prompt: str, normalized_cart_names: List[str], strict_retry: bool = False,
) -> Optional[Dict[str, Any]]:
    """One generation attempt -> parse -> compute coverage -> validate (Task G4).
    Returns None on any failure (a raised exception, an unparseable response, zero
    ingredient overlap with the cart, or a validation failure) so the caller can decide
    whether to retry or give up -- never partially-built or unvalidated data."""
    try:
        answer = pipeline.generator.generate(
            prompt, "(no matching reference recipe found)", build_meal_ideas_system_prompt(strict_retry=strict_retry),
            options={"temperature": GENERATION_TEMPERATURE},
        )
    except Exception as e:
        logger.error(f"Meal-idea generation failed: {e}")
        return None

    sections = _parse_recipe_sections(answer)
    ingredients_block = sections.get("ingredients")
    if not ingredients_block:
        return None
    raw_ingredients = _split_generated_ingredient_lines(ingredients_block)
    structured = structure_ingredients(raw_ingredients)
    required = structured["required_ingredients"]
    optional = structured["optional_ingredients"]

    required_names = [ing["name"] for ing in required]
    coverage = compute_coverage(required_names, normalized_cart_names)
    if not coverage["matched_cart_names"]:
        return None

    missing = coverage["missing_required_ingredients"]
    idea = {
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
    }
    if not validate_generated_idea(idea, normalized_cart_names):
        return None
    return idea


def _generate_fallback_ideas(
    pipeline: RecipeRAGPipeline, normalized_cart_names: List[str], max_results: int
) -> Tuple[List[Dict[str, Any]], bool]:
    """Task C3's fallback path -- only reached when retrieval returns nothing usable.
    Mirrors find_recipes_or_generate()'s "one angle per call" mechanism (see that
    function's own comment for why: OpenWebUI silently pins temperature, native Ollama
    doesn't) but with the shared meal-ideas policy from ai_policy.py (Epic G).

    Task G4: a generation that fails validation is retried once under a stricter
    prompt; if that also fails, the angle is simply skipped (a safe fallback -- never
    return something malformed as if it were a valid idea).

    Returns (ideas, validation_failure) -- the second element is Epic J1's
    validation_failure signal: True if any angle's first attempt needed the stricter
    retry, regardless of whether that retry then succeeded."""
    ingredients_str = ", ".join(normalized_cart_names)
    n = min(max_results, len(_GENERATION_ANGLES))
    ideas: List[Dict[str, Any]] = []
    validation_failure = False

    for i in range(n):
        prompt = _GENERATION_ANGLES[i].format(ing=ingredients_str)
        idea = _generate_one_idea(pipeline, prompt, normalized_cart_names)
        if idea is None:
            validation_failure = True
            idea = _generate_one_idea(pipeline, prompt, normalized_cart_names, strict_retry=True)
        if idea is not None:
            ideas.append(idea)

    return ideas, validation_failure


def _generate_ideas_from_eligible_rows(
    pipeline: RecipeRAGPipeline,
    eligible_rows: List[Dict[str, Any]],
    max_results: int,
) -> Dict[str, Any]:
    """Shared core of both entry points below (Task C1-C8's pipeline, now also Epic
    E's from-store flow): given rows already resolved and filtered to recipe_eligible,
    normalize/dedupe -> retrieve corpus candidates first -> fall back to generation only
    if retrieval finds nothing usable -> rank -> cap at max_results. Callers own
    resolving their own source (cart item ids vs. one store's offers) and attach their
    own excluded-items field to the result -- this only ever sees what already passed
    eligibility.

    The returned dict also carries two internal-only keys, `_retrieved_candidate_count`
    and `_validation_failure` (Epic J1's log fields, underscore-prefixed since neither
    is part of Task C7's documented response shape) -- callers below must pop() both
    before returning the result to an HTTP caller."""
    # A request body's max_results can be an explicit JSON `null`, not just an omitted
    # field -- Pydantic's `Optional[int] = 5` only applies that default when the key is
    # missing entirely, so None can and does reach here otherwise. Left unguarded,
    # _generate_fallback_ideas's `min(max_results, ...)` raises a TypeError against
    # None (confirmed: this crashed both /meal-ideas/from-cart and /meal-ideas/from-store).
    if max_results is None:
        max_results = 5

    # Task C8: zero eligible ingredients -- never call retrieval/generation with an
    # empty query, just report nothing to suggest.
    if not eligible_rows:
        return {"ideas": [], "source": None, "_retrieved_candidate_count": 0, "_validation_failure": False}

    name_pairs = normalize_and_dedupe(eligible_rows)
    normalized_names = [normalized for _, normalized in name_pairs]

    grounded = pipeline.find_recipes_from_ingredients(
        normalized_names, max_results=_CANDIDATE_POOL_SIZE, normalize=False,
    )

    ideas = []
    for result in grounded:
        idea = _build_idea_from_corpus_result(result, normalized_names)
        if idea is not None:
            ideas.append(idea)

    source_type = "retrieved"
    validation_failure = False
    if not ideas:
        # Task C3: generation is the fallback, only reached when retrieval produced
        # nothing usable.
        ideas, validation_failure = _generate_fallback_ideas(pipeline, normalized_names, max_results)
        source_type = "generated"

    ideas.sort(key=_rank_key)
    return {
        "ideas": ideas[:max_results],
        # Not part of Task C7's documented response shape, but a cheap, useful signal
        # for the app/logs to know which branch produced these ideas without having to
        # inspect every individual idea's own source_type.
        "source": source_type if ideas else None,
        "_retrieved_candidate_count": len(grounded),
        "_validation_failure": validation_failure,
    }


def _top_idea_coverage(ideas: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[int]]:
    """Epic J1's ingredient_coverage/missing_ingredient_count fields summarize the
    whole request with the top-ranked idea (ideas[0], already the best-ranked by
    _rank_key) as the representative result -- logging every returned idea's coverage
    separately would be a list-of-lists per event for no real benefit at this stage."""
    if not ideas:
        return None, None
    top = ideas[0]
    return top["ingredient_coverage_percentage"], len(top["missing_required_ingredients"])


def generate_meal_ideas_from_cart(
    pipeline: RecipeRAGPipeline,
    discounts: List[Dict[str, Any]],
    discount_item_ids: List[str],
    max_results: int = 5,
    language: str = "en",
    discount_snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Orchestrates the full Task C1-C8 pipeline -- see module docstring for the
    numbered steps. `language` is accepted for API-shape consistency with the rest of
    pipeline_server.py's endpoints but not yet applied here -- meal ideas aren't
    translated to Norwegian in this first version (Epic C's own acceptance criteria
    don't require it); wiring it through translator.py the same way
    find_recipes_or_generate() does is straightforward follow-up work once needed.
    `discount_snapshot_id` is passed through only for Epic J1's log event -- pipeline_
    server.py is the only thing that knows which cached snapshot it fetched. The
    response's own `request_id` (Epic J3) lets the app attach later "Helpful"/"Not
    helpful" feedback to the exact request that produced these ideas, without the app
    having to resend the full recommendation inputs/outputs itself."""
    started_at = time.perf_counter()
    request_id = new_request_id()
    resolved_rows, not_found = resolve_cart_items(discount_item_ids, discounts)
    eligible_rows, ineligible = filter_eligible_items(resolved_rows)

    result = _generate_ideas_from_eligible_rows(pipeline, eligible_rows, max_results)
    retrieved_candidate_count = result.pop("_retrieved_candidate_count")
    validation_failure = result.pop("_validation_failure")
    excluded = not_found + ineligible
    result["excluded_cart_items"] = excluded
    result["request_id"] = request_id

    coverage, missing_count = _top_idea_coverage(result["ideas"])
    log_recommendation_event(
        request_id=request_id,
        recommendation_type="cart",
        selected_product_ids=list(discount_item_ids),
        eligible_product_ids=[row.get("product_name") for row in eligible_rows],
        excluded_product_ids=[item.get("product_name") for item in excluded],
        retrieved_candidate_count=retrieved_candidate_count,
        generated_fallback_used=result["source"] == "generated",
        meal_ideas_returned=len(result["ideas"]),
        ingredient_coverage=coverage,
        missing_ingredient_count=missing_count,
        discount_snapshot_id=discount_snapshot_id,
        latency_seconds=time.perf_counter() - started_at,
        validation_failure=validation_failure,
    )
    return result


def generate_meal_ideas_from_store(
    pipeline: RecipeRAGPipeline,
    discounts: List[Dict[str, Any]],
    store_name: str,
    max_results: int = 5,
    language: str = "en",
    discount_snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Epic E (Task E2/E4): same corpus-first/generation-fallback pipeline as the cart
    flow above, sourced from one store's current cached offers instead of the user's
    cart -- never triggers a new Tjek scan, reclassification, or discount re-analysis
    (resolve_store_items() only filters the already-cached snapshot). `language` is
    accepted for the same API-shape-consistency reason as the cart flow above and
    likewise not yet applied. `discount_snapshot_id` is Epic J1's log field, same as
    the cart flow above. The response's own `request_id` (Epic J3) is the same
    feedback-correlation mechanism as the cart flow above."""
    started_at = time.perf_counter()
    request_id = new_request_id()
    store_rows = resolve_store_items(store_name, discounts)
    eligible_rows, ineligible = filter_eligible_items(store_rows)

    result = _generate_ideas_from_eligible_rows(pipeline, eligible_rows, max_results)
    retrieved_candidate_count = result.pop("_retrieved_candidate_count")
    validation_failure = result.pop("_validation_failure")
    result["excluded_store_items"] = ineligible
    result["store_name"] = store_name
    result["request_id"] = request_id

    coverage, missing_count = _top_idea_coverage(result["ideas"])
    log_recommendation_event(
        request_id=request_id,
        recommendation_type="store",
        selected_product_ids=[row.get("product_name") for row in store_rows],
        eligible_product_ids=[row.get("product_name") for row in eligible_rows],
        excluded_product_ids=[item.get("product_name") for item in ineligible],
        retrieved_candidate_count=retrieved_candidate_count,
        generated_fallback_used=result["source"] == "generated",
        meal_ideas_returned=len(result["ideas"]),
        ingredient_coverage=coverage,
        missing_ingredient_count=missing_count,
        discount_snapshot_id=discount_snapshot_id,
        latency_seconds=time.perf_counter() - started_at,
        validation_failure=validation_failure,
    )
    return result

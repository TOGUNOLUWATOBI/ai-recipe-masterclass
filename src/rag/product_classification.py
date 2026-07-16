"""Shared classification schema for grocery discount products (Epic A of the
post-user-testing change spec) -- the richer replacement for the old flat
"main_food" / "snack" / "non_food" category grocery_discounts.classify_product()
and product_classifier.py used to produce.

Every classifier (the keyword heuristic in grocery_discounts.py, the LLM tier in
product_classifier.py, and the manual override list below) ultimately produces a
`ProductClassification`: a `shopping_group` + `food_usage_class` + `meal_role`,
with `recipe_eligible` / `recipe_exclusion_reason` always *derived* from those
via build_classification() rather than asked of the classifier directly -- this
is what guarantees eligibility can never drift out of sync between the heuristic
and LLM paths, or between two different classifier versions.

A product is recipe_eligible only when it's a primary_ingredient or
supporting_ingredient. Every other food_usage_class (ready_meal, ready_to_eat,
beverage, snack_or_treat, unknown) is excluded -- these are still real food
(they still show up in the app's Food section, see the mobile app's cart/store
screens), just not something a recipe generator should ever be handed. See the
change spec's Epic A worked examples: chicken/canned beans/pasta sauce should be
usable; Coca-Cola/frozen pizza/chocolate/ready-made lasagne should not.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).resolve().parent
MANUAL_OVERRIDES_PATH = RAG_DIR / "manual_product_overrides.json"

SHOPPING_GROUPS = ("food", "non_food")

FOOD_USAGE_CLASSES = (
    "primary_ingredient",
    "supporting_ingredient",
    "ready_meal",
    "ready_to_eat",
    "beverage",
    "snack_or_treat",
    "unknown",
    "not_applicable",
)

MEAL_ROLES = (
    "protein",
    "carbohydrate",
    "vegetable",
    "fruit",
    "dairy",
    "pantry",
    "sauce_or_condiment",
    "bread_or_bakery",
    "other",
    "not_applicable",
)

RECIPE_EXCLUSION_REASONS = (
    "non_food",
    "beverage",
    "finished_meal",
    "snack_or_treat",
    "insufficient_confidence",
    "other",
)

# "heuristic" (grocery_discounts.classify_product), "llm" (product_classifier.py),
# or "manual_override" (this module) -- stored per-product in
# discounts_store.product_classifications so low-quality classifications can be
# tracked back to their source (see Epic J's "most frequently corrected products").
CLASSIFICATION_SOURCES = ("heuristic", "llm", "manual_override")

# Bumped whenever the classification prompt/schema/keyword lists change in a way
# that would make previously-cached classifications worth revisiting -- stored
# alongside each cached row (see discounts_store.product_classifications) so a
# future migration can tell "classified under the old rules" apart from "classified
# under the current ones" instead of having to guess from classified_at alone.
CLASSIFIER_VERSION = "epic-a-v1"

# food_usage_class values a recipe generator may actually use as an ingredient.
# Everything else is real food (still shown in the app) but excluded from meal
# generation -- see the module docstring.
_ELIGIBLE_USAGE_CLASSES = ("primary_ingredient", "supporting_ingredient")

_EXCLUSION_REASON_BY_USAGE_CLASS = {
    "ready_meal": "finished_meal",
    "ready_to_eat": "finished_meal",
    "beverage": "beverage",
    "snack_or_treat": "snack_or_treat",
    "unknown": "insufficient_confidence",
}


class ProductClassification(TypedDict):
    shopping_group: str
    food_usage_class: str
    meal_role: str
    recipe_eligible: bool
    recipe_exclusion_reason: Optional[str]


def build_classification(
    shopping_group: str, food_usage_class: str, meal_role: str = "other"
) -> ProductClassification:
    """The single place recipe_eligible / recipe_exclusion_reason get computed --
    every classifier (heuristic, LLM, manual override) calls this instead of
    deciding eligibility itself, so the two fields can never disagree with each
    other or drift between classifier versions.

    meal_role is only kept for food_usage_class values that are actually
    eligible (primary_ingredient / supporting_ingredient) -- a role like
    "protein" or "pantry" isn't meaningful for a beverage or a ready meal, so
    everything else collapses to "not_applicable" regardless of what's passed in.
    """
    if shopping_group == "non_food":
        return {
            "shopping_group": "non_food",
            "food_usage_class": "not_applicable",
            "meal_role": "not_applicable",
            "recipe_eligible": False,
            "recipe_exclusion_reason": "non_food",
        }

    eligible = food_usage_class in _ELIGIBLE_USAGE_CLASSES
    return {
        "shopping_group": "food",
        "food_usage_class": food_usage_class,
        "meal_role": meal_role if eligible else "not_applicable",
        "recipe_eligible": eligible,
        "recipe_exclusion_reason": None if eligible else _EXCLUSION_REASON_BY_USAGE_CLASS.get(food_usage_class, "other"),
    }


# The default-exclude outcome for a product the classifier genuinely couldn't
# place with confidence (see product_classifier.py's confidence="low" handling)
# -- "Important rule" in Epic A: uncertainty excludes a product from meal
# generation, it does not default it to eligible. The product can still appear
# in the cart (shopping_group stays "food", not "non_food").
UNKNOWN_CLASSIFICATION: ProductClassification = build_classification("food", "unknown")


def legacy_category(classification: ProductClassification) -> str:
    """Derives the old 3-way "main_food" / "snack" / "non_food" label the mobile
    app's existing Food/Non-food tab split and Food/Snacks section grouping
    already read (see mobile-app/src/screens/StoresScreen.tsx and
    StoreItemsScreen.tsx) -- kept so the richer classification below is
    additive, not a breaking API change. Always derived, never stored
    independently, so it can't silently drift from the classification it's
    describing."""
    if classification["shopping_group"] == "non_food":
        return "non_food"
    if classification["food_usage_class"] in ("beverage", "snack_or_treat"):
        return "snack"
    return "main_food"


def load_manual_overrides() -> Dict[str, ProductClassification]:
    """Loads the small hand-maintained override list (Epic A5) -- products that
    are frequently misclassified by the heuristic or the LLM and are corrected
    here directly instead of by repeatedly tweaking prompts or keyword lists for
    one product at a time. Keyed by the exact product name as Tjek publishes it
    (headings are already upper-case in practice, but matching is exact/
    case-sensitive on purpose -- see the module docstring in
    manual_product_overrides.json for why a normalized/fuzzy key was rejected).

    Missing file or malformed JSON is treated as "no overrides configured" --
    this list is optional polish, not load-bearing infrastructure, so a typo in
    it should never take down a discount refresh."""
    if not MANUAL_OVERRIDES_PATH.exists():
        return {}
    try:
        raw = json.loads(MANUAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read manual product overrides, ignoring: {e}")
        return {}

    overrides: Dict[str, ProductClassification] = {}
    for product_name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        shopping_group = entry.get("shopping_group")
        food_usage_class = entry.get("food_usage_class", "not_applicable")
        meal_role = entry.get("meal_role", "other")
        if shopping_group not in SHOPPING_GROUPS:
            logger.warning(f"Skipping manual override for {product_name!r}: invalid shopping_group {shopping_group!r}")
            continue
        overrides[product_name] = build_classification(shopping_group, food_usage_class, meal_role)
    return overrides


def validate_llm_entry(entry: Dict[str, Any]) -> Optional[ProductClassification]:
    """Validates one classification model response entry against the schema
    (Epic A3 step 4) before it's trusted. Returns None -- never a guessed
    fallback -- for anything malformed, so the caller can fall back to whatever
    the heuristic already produced for that product rather than store a
    half-valid guess permanently."""
    shopping_group = entry.get("shopping_group")
    food_usage_class = entry.get("food_usage_class")
    meal_role = entry.get("meal_role", "other")
    confidence = entry.get("confidence")

    if shopping_group not in SHOPPING_GROUPS:
        return None
    if food_usage_class not in FOOD_USAGE_CLASSES:
        return None
    if meal_role not in MEAL_ROLES:
        meal_role = "other"

    # A model that reports low confidence in its own call is exactly the
    # "ambiguous" case Epic A3's important rule is about -- treat it as unknown
    # (excluded, but still cacheable as a deliberate answer) rather than trust
    # a guess it already told us not to trust.
    if confidence == "low":
        food_usage_class = "unknown"

    return build_classification(shopping_group, food_usage_class, meal_role)

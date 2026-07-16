"""LLM-based grocery-item classification (Epic A) -- a more accurate alternative to
grocery_discounts.py's keyword heuristic (classify_product()), used to backfill the
full ProductClassification (shopping_group, food_usage_class, meal_role -- see
product_classification.py) for products discounts_store.py's product_classifications
cache hasn't seen before. A product is only ever sent here once and then cached
forever (see refresh_discounts.py), so the added latency/cost is bounded by how many
genuinely new product names show up each scan, not the full ~800-item catalog every
time.

Confirmed live (2026-07-15) against qwen3:8b with think=False: correctly classified
several real headings the old flat keyword heuristic missed entirely -- "SØRLANDSIS"
-> snack, "KRONE-IS" -> snack, "Kvikk Lunsj" -> snack (none of these have a Norwegian
keyword generic enough to catch safely), and "FACE CONTROL CREAM" -> non_food (not
Norwegian at all). Deliberately NOT config.LLM_MODEL (toriko3, fine-tuned specifically
for recipe generation/QA) -- a recipe-fine-tuned model is a poor fit for a generic
structured-classification task; qwen3:8b is a general-purpose instruction model
already pulled on the Mac mini. think=False matters: qwen3's default "thinking" mode
adds several seconds of reasoning tokens for a task this simple, and qwen3.5:9b-nothink
was checked live and still emitted thinking content despite the tag name -- think=False
is a real Ollama chat parameter (confirmed supported by the installed ollama client)
that actually disables it, and format=_RESPONSE_SCHEMA (also a real, confirmed-live
supported parameter) constrains the response to valid JSON instead of relying on
prompt wording alone.

Epic A extends this from a single "main_food"/"snack"/"non_food" label to the full
classification schema, plus a self-reported confidence -- see
product_classification.validate_llm_entry() for why confidence="low" is folded into
food_usage_class="unknown" (and therefore excluded from recipe generation) rather than
trusted at face value. Never crashes the caller and never poisons the cache with a
malformed guess: any failure (Ollama unreachable, malformed JSON, one item missing or
failing schema validation) just omits that product from the returned dict. The
caller's own keyword-heuristic classification (already computed by
find_discounted_products() for every item) is what's used instead for anything
missing here -- and since nothing gets written to the permanent cache for an omitted
item, it's retried by the LLM on the next refresh rather than being stuck with the
weaker fallback forever just because Ollama happened to be down once."""

import json
import logging
from typing import Dict, List

from .generator import RecipeGenerator
from .product_classification import (
    FOOD_USAGE_CLASSES,
    MEAL_ROLES,
    ProductClassification,
    SHOPPING_GROUPS,
    validate_llm_entry,
)

logger = logging.getLogger(__name__)

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "shopping_group": {"type": "string", "enum": list(SHOPPING_GROUPS)},
                    "food_usage_class": {"type": "string", "enum": list(FOOD_USAGE_CLASSES)},
                    "meal_role": {"type": "string", "enum": list(MEAL_ROLES)},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["index", "shopping_group", "food_usage_class", "confidence"],
            },
        },
    },
    "required": ["classifications"],
}

# Mirrors the classification meanings from Epic A's change spec verbatim, including
# the "don't just exclude everything processed" guidance (Task A2) -- canned/frozen/
# jarred staples are extremely common real recipe ingredients in Norwegian flyers and
# a naive "processed = excluded" rule would wrongly exclude most of a normal pantry.
_PROMPT_TEMPLATE = """Classify each numbered Norwegian grocery flyer product name for a recipe app.

For each product, decide:
- shopping_group: "food" or "non_food"
- food_usage_class (only for food):
  - primary_ingredient: forms a meaningful part of a meal on its own (chicken, beef, fish, potatoes, rice, pasta, carrots, broccoli, eggs, tofu, ...)
  - supporting_ingredient: used in cooking but unlikely to form a meal alone (canned tomatoes, coconut milk, cooking cream, beans, cheese, bread, stock cubes, pasta sauce, flour, herbs, ...)
  - ready_meal: a substantially complete meal meant to be heated or eaten directly (frozen pizza, ready-made lasagne, microwave curry, prepared soup, ready-made sandwiches, prepared sushi, ...)
  - ready_to_eat: a finished food product not normally used as a cooking input (prepared salad bowl, breakfast yoghurt cup, packaged smoothie, pre-made dessert, ...)
  - beverage: a drink (soda, juice, energy drink, bottled water, beer, ...)
  - snack_or_treat: food that isn't a recipe ingredient (chocolate, crisps, ice cream, sweets, biscuits, ...)
  - unknown: you cannot confidently place this product in any of the above
- meal_role (only when food_usage_class is primary_ingredient or supporting_ingredient): protein, carbohydrate, vegetable, fruit, dairy, pantry, sauce_or_condiment, bread_or_bakery, or other
- confidence: "high", "medium", or "low" -- use "low" whenever you are genuinely unsure, rather than guessing a specific class

Important: classify by whether the product is actually useful as a cooking ingredient,
not by whether it has been processed -- canned tomatoes, canned beans, frozen
vegetables, coconut milk, pasta sauce, stock, and grated cheese are all normal
supporting_ingredient products despite being processed.

Return one entry per index, covering every index below.

{numbered_names}"""


def _build_prompt(product_names: List[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(product_names))
    return _PROMPT_TEMPLATE.format(numbered_names=numbered)


def classify_batch(generator: RecipeGenerator, product_names: List[str]) -> Dict[str, ProductClassification]:
    """Classifies one batch in a single LLM call. Returns only entries the LLM
    actually classified successfully and that passed schema validation -- see module
    docstring for why a missing/invalid name is left to the caller's fallback rather
    than guessed here."""
    if not product_names:
        return {}

    try:
        content = generator.chat(
            [{"role": "user", "content": _build_prompt(product_names)}],
            think=False,
            format=_RESPONSE_SCHEMA,
        )
        parsed = json.loads(content)
    except Exception as e:
        logger.warning(
            f"LLM classification call failed for a batch of {len(product_names)} products "
            f"(falling back to the keyword heuristic this run, will retry next refresh): {e}"
        )
        return {}

    result: Dict[str, ProductClassification] = {}
    for entry in parsed.get("classifications", []):
        index = entry.get("index")
        if not isinstance(index, int) or not (1 <= index <= len(product_names)):
            continue
        classification = validate_llm_entry(entry)
        if classification is None:
            continue
        result[product_names[index - 1]] = classification
    return result


def classify_new_products(
    generator: RecipeGenerator, product_names: List[str], batch_size: int = 30
) -> Dict[str, ProductClassification]:
    """Classifies every (deduplicated) name in product_names, one LLM call per
    batch_size-sized chunk. Callers should only pass names not already in
    discounts_store's product_classifications cache -- this always calls the LLM
    regardless of what's cached, the cache check is refresh_discounts.py's job, not
    this module's."""
    unique_names = list(dict.fromkeys(product_names))  # de-dup, preserve order
    result: Dict[str, ProductClassification] = {}
    for i in range(0, len(unique_names), batch_size):
        batch = unique_names[i : i + batch_size]
        result.update(classify_batch(generator, batch))
    return result

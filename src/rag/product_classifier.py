"""LLM-based grocery-item classification -- a more accurate alternative to
grocery_discounts.py's keyword heuristic (classify_product()), used to backfill
categories for products discounts_store.py's product_categories cache hasn't seen
before. A product is only ever sent here once and then cached forever (see
refresh_discounts.py), so the added latency/cost is bounded by how many genuinely new
product names show up each scan, not the full ~800-item catalog every time.

Confirmed live (2026-07-15) against qwen3:8b with think=False: correctly classified
several real headings the keyword heuristic missed entirely -- "SØRLANDSIS" -> snack,
"KRONE-IS" -> snack, "Kvikk Lunsj" -> snack (none of these have a Norwegian keyword
generic enough to catch safely), and "FACE CONTROL CREAM" -> non_food (not Norwegian
at all). Deliberately NOT config.LLM_MODEL (toriko3, fine-tuned specifically for
recipe generation/QA) -- a recipe-fine-tuned model is a poor fit for a generic
structured-classification task; qwen3:8b is a general-purpose instruction model
already pulled on the Mac mini. think=False matters: qwen3's default "thinking" mode
adds several seconds of reasoning tokens for a task this simple, and qwen3.5:9b-nothink
was checked live and still emitted thinking content despite the tag name -- think=False
is a real Ollama chat parameter (confirmed supported by the installed ollama client)
that actually disables it, and format=_RESPONSE_SCHEMA (also a real, confirmed-live
supported parameter) constrains the response to valid JSON instead of relying on
prompt wording alone.

Never crashes the caller and never poisons the cache with a low-confidence guess: any
failure (Ollama unreachable, malformed JSON, one item missing from the response) just
omits that product from the returned dict. The caller's own keyword-heuristic category
(already computed by find_discounted_products() for every item) is what's used instead
for anything missing here -- and since nothing gets written to product_categories for
an omitted item, it's retried by the LLM on the next refresh rather than being stuck
with the weaker fallback forever just because Ollama happened to be down once."""

import json
import logging
from typing import Dict, List

from .generator import RecipeGenerator

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = ("main_food", "non_food", "snack")

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "category": {"type": "string", "enum": list(_VALID_CATEGORIES)},
                },
                "required": ["index", "category"],
            },
        },
    },
    "required": ["classifications"],
}

_PROMPT_TEMPLATE = """Classify each numbered Norwegian grocery flyer product name as exactly one of:
- main_food: a real recipe ingredient (meat, produce, dairy, pantry staples, ...)
- snack: food, but not something a recipe would call for (candy, chips, soda, ice cream, cookies, ...)
- non_food: not food at all (cleaning products, hygiene items, pet food, garden/BBQ gear, flowers, ...)

Return one entry per index, covering every index below.

{numbered_names}"""


def _build_prompt(product_names: List[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(product_names))
    return _PROMPT_TEMPLATE.format(numbered_names=numbered)


def classify_batch(generator: RecipeGenerator, product_names: List[str]) -> Dict[str, str]:
    """Classifies one batch in a single LLM call. Returns only entries the LLM
    actually classified successfully -- see module docstring for why a missing name
    is left to the caller's fallback rather than guessed here."""
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

    result: Dict[str, str] = {}
    for entry in parsed.get("classifications", []):
        index = entry.get("index")
        category = entry.get("category")
        if not isinstance(index, int) or not (1 <= index <= len(product_names)):
            continue
        if category not in _VALID_CATEGORIES:
            continue
        result[product_names[index - 1]] = category
    return result


def classify_new_products(
    generator: RecipeGenerator, product_names: List[str], batch_size: int = 30
) -> Dict[str, str]:
    """Classifies every (deduplicated) name in product_names, one LLM call per
    batch_size-sized chunk. Callers should only pass names not already in
    discounts_store's product_categories cache -- this always calls the LLM regardless
    of what's cached, the cache check is refresh_discounts.py's job, not this
    module's."""
    unique_names = list(dict.fromkeys(product_names))  # de-dup, preserve order
    result: Dict[str, str] = {}
    for i in range(0, len(unique_names), batch_size):
        batch = unique_names[i : i + batch_size]
        result.update(classify_batch(generator, batch))
    return result

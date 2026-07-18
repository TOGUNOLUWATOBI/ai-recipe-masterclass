"""Epic G: the shared everyday-meal generation policy applied wherever the meal-ideas
pipeline (Epic C/E) falls back to LLM generation -- rag/meal_ideas.py's
_generate_fallback_ideas() is the one caller today.

Deliberately scoped to that fallback path specifically, not to pipeline.py's own
general-purpose recipe generation (/query, /recipes/from-ingredients,
/recipes/discounted) -- that's a separate, already-shipped prompt/flow with a different
job (answer an arbitrary question, or generate a recipe for one specific product), and
Epic G's own acceptance criteria are explicitly "carried by Epic C's acceptance
criteria" in the source spec, not a mandate to rewrite pipeline.py's SYSTEM_PROMPT.

Four things live here:
  1. EVERYDAY_MEAL_POLICY (Task G1) -- the rule set: familiar/simple meals, never treat
     an ineligible product as an ingredient, separate required from optional, never
     claim store availability or invent a price/discount/product/store.
  2. FEW_SHOT_EXAMPLES (Task G2) -- three worked examples baked directly into the
     system prompt (generator.py's _build_messages() only supports one system + one
     user message, so "few-shot via separate turns" isn't available without a larger
     interface change -- embedding worked examples as text in the system prompt is the
     standard fallback technique and is what's implemented here).
  3. GENERATION_TEMPERATURE (Task G3) -- lower than the general multi-recipe-suggestion
     flow's diversity-oriented temperature, since everyday cart/store planning wants a
     predictable, ordinary result, not maximum variety. The existing high-temperature
     "give me something different" flow (pipeline.py) is untouched and kept as the
     explicit escape hatch the story calls for.
  4. validate_generated_idea() (Task G4) -- checked before a generated idea is ever
     returned; a caller should retry once under a stricter prompt suffix
     (STRICT_RETRY_SUFFIX) and, if that still fails, drop the idea rather than return
     something malformed. Most of what G4 asks for (every mentioned product being
     recipe-eligible, required/optional arrays existing, nothing both missing and
     available) is already structurally guaranteed by this pipeline's own construction
     -- ineligible products never reach the prompt at all (Task C2), and
     selected/missing sets are computed deterministically, never by the LLM (Task C4) --
     so this validator is a defense-in-depth safety net against a future regression or a
     genuinely malformed generation, not a currently-reachable failure mode.
"""

from typing import Any, Dict, List

EVERYDAY_MEAL_POLICY = """You are an everyday home-cooking assistant helping someone plan a meal from groceries they already have.

STRICT RULES:
1. Suggest a practical, familiar meal an ordinary home cook would actually make -- never a restaurant-style, deconstructed, or unusually creative dish.
2. You do not have to use every ingredient listed -- use whichever subset makes one sensible, coherent meal, and ignore the rest. If nothing sensible uses more than one or two of them, that's fine too.
3. Never invent an ingredient that isn't listed and isn't a basic pantry staple (salt, water, cooking oil, pepper).
4. Only treat an ingredient as usable if it was actually given to you in the ingredient list below -- never assume a beverage, snack, non-food item, or ready-made meal is available just because it's a common grocery item, and never suggest one as an ingredient unless it is explicitly listed and genuinely required by the dish.
5. Clearly separate the ingredients you actually use into what the dish truly needs versus anything that's a nice-to-have addition.
6. Never state or imply that a specific store currently stocks or sells an ingredient, and never invent a price, a discount, a product name, or a store name -- you have no access to real-time store or pricing data, so any such claim would be fabricated.
7. Present the ingredients you actually use as a simple, clean bulleted list, and the steps as a numbered list.
8. Keep instructions short and plain: about 4 to 8 steps, ordinary short sentences, no professional culinary terms, no plating direction, and never describe the dish as "gourmet", "elevated", or "restaurant-quality".
9. Use only standard, plain English text. Never use R-programming syntax (like c(), quotes, or brackets around lists).
10. Do not include conversational filler."""

# Task G2: anchors the model's behavior by demonstration, not description alone. Kept
# short and generic (not tied to a specific cuisine/corpus) since these are meant to
# illustrate the *rules* above, not to bias the model toward one particular dish.
FEW_SHOT_EXAMPLES = """EXAMPLES:

Example 1 (good output) -- given: chicken breast, rice, onion
Title: Chicken and Rice Skillet
Ingredients:
- chicken breast
- rice
- onion
Instructions:
1. Dice the onion and cook it in a pan with a little oil until soft.
2. Cut the chicken breast into pieces and add it to the pan.
3. Cook until the chicken is browned on all sides.
4. Add the rice and enough water to cook it through, following the package instructions.
5. Simmer until the rice is tender and the liquid is absorbed.
6. Season with salt and pepper to taste and serve.

Example 2 (exclusion) -- given: chicken breast, rice, Coca-Cola, chocolate bar
Only chicken breast and rice are real cooking ingredients here -- Coca-Cola and the chocolate bar are a drink and a snack, not something a home cook would build a meal around, so the suggestion only uses chicken and rice and ignores the other two entirely, the same as Example 1 above.

Example 3 (do not force a combination) -- given: salmon fillet, taco shells, yoghurt
These three don't belong in one sensible dish together. Rather than inventing an unusual combination that uses all three, it's better to suggest a plain salmon dish using just the salmon (and ignore the taco shells and yoghurt), or say there isn't one sensible everyday meal that uses all of them. Never force every listed ingredient into a single dish just because it was listed."""

# Task G3: lower than the general multi-recipe flow's diversity-oriented temperature --
# everyday cart/store planning wants a predictable, ordinary result, variety comes from
# retrieval candidates and the different angles in _GENERATION_ANGLES, not raw
# randomness. Kept within the spec's suggested 0.3-0.6 range.
GENERATION_TEMPERATURE = 0.5

# Task G4: appended to the system prompt on a validation-failure retry -- reinforces
# the two rules a malformed generation is most likely to have broken (inventing an
# ingredient, or refusing to leave anything out).
STRICT_RETRY_SUFFIX = """

IMPORTANT -- your previous attempt did not follow the rules above. Try again, and this time:
- Only mention ingredients that were actually listed, plus basic pantry staples (salt, water, cooking oil, pepper).
- Give a real title and a real ingredients list -- do not leave either empty.
- It's fine, and often correct, to use only some of the listed ingredients."""


def build_meal_ideas_system_prompt(strict_retry: bool = False) -> str:
    """Task G1/G2: the full system prompt for one meal-ideas generation call --
    policy + few-shot examples, optionally with the stricter retry suffix (Task G4)
    appended after a first attempt failed validation."""
    prompt = f"{EVERYDAY_MEAL_POLICY}\n\n{FEW_SHOT_EXAMPLES}"
    if strict_retry:
        prompt += STRICT_RETRY_SUFFIX
    return prompt


def validate_generated_idea(idea: Dict[str, Any], normalized_cart_names: List[str]) -> bool:
    """Task G4: checked before a generated idea is ever returned to a caller. Returns
    False for anything a caller should treat as malformed and retry/drop rather than
    show to a user. Defense-in-depth: most of these invariants are already guaranteed
    by how meal_ideas.py constructs an idea (see module docstring), but a future change
    to that construction, or a genuinely broken generation, should never slip through
    silently."""
    if not idea.get("title"):
        return False
    if not idea.get("required_ingredients"):
        return False

    selected = set(idea.get("selected_items_used") or [])
    missing = set(idea.get("missing_required_ingredients") or [])
    # Nothing may be listed as both used and missing at once.
    if selected & missing:
        return False

    # Every "used" ingredient must actually be one of the real, eligible cart/store
    # names this generation call was given -- never a name the model introduced itself.
    cart_names = set(normalized_cart_names)
    if not selected.issubset(cart_names):
        return False

    return True

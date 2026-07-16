"""Epic D: splits a recipe's raw ingredient lines into required vs. optional
{name, quantity} pairs, and filters out assumed pantry basics -- the "structured
recipe responses" half of Task D1, applied uniformly to both corpus recipes (real
ingredient lines, see recipe_loader.py) and generated recipes (parsed from the LLM's
bulleted **Ingredients:** block, see meal_ideas.py's _split_generated_ingredient_lines())
since both reduce to the same List[str] of ingredient lines by the time they reach here.

This is a per-line, marker-based heuristic, not an ingredient-understanding model --
same honesty as grocery_terms.py's own suffix-matching glossary: good enough to
separate "2 tbsp coarse sea salt" (a pantry basic) from "2 tbsp garlic salt" (a real,
distinct seasoning) and "1 tsp black pepper" (optional per Task D3's own example) from
"2 chicken breasts" (required), without a full NLP ingredient parser that doesn't
exist in this codebase. Known gaps are called out inline below rather than silently
shipped.

Task D2 (required): the default for any ingredient line not caught by one of the two
rules below -- absent a signal to the contrary, a listed ingredient is assumed
essential to the dish.

Task D3 (optional): an explicit textual marker ("optional", "to taste", "for garnish",
...), OR the ingredient's core identity is one of D3's own named examples of a pantry
seasoning addition (pepper, chilli) even with no marker in the text. Capped at 5 (D3's
own "recommended maximum") -- overflow is demoted back into required rather than
silently dropped, since every real ingredient line must end up somewhere.

Task D5 (pantry basics): water, salt, and (generic) cooking oil are filtered out of
both lists entirely and never shown as an ingredient a user has to source -- flavor-
specific oils (olive, sesame, coconut, ...) are deliberately NOT matched, since those
carry real dish-identity signal a generic "cooking oil" assumption doesn't. The
"Assumed pantry basics" note itself (PANTRY_BASICS_NOTE) is a fixed, always-shown
disclaimer, not conditional on whether this particular recipe happened to name one --
plenty of recipes imply salt ("season to taste") without ever naming it.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# Task D5's literal MVP list -- deliberately small and specific. Shown to the user
# verbatim regardless of what any individual recipe's ingredients mention (see module
# docstring) -- configurable here if the assumption ever needs to grow.
PANTRY_BASICS_NOTE = ("salt", "water", "cooking oil")

# Broader than PANTRY_BASICS_NOTE above -- every *core phrase* (see _core_phrase())
# that should be filtered out of an ingredient list as "assumed available," including
# generic synonyms for the same three basics ("vegetable oil"/"neutral oil" both mean
# the same "basic cooking oil" concept to an ordinary home cook). A flavor-specific
# oil (olive, sesame, coconut, ...) never reduces to one of these phrases, since its
# own name survives qualifier-stripping below.
_PANTRY_BASIC_CORE_PHRASES = ("water", "salt", "oil", "cooking oil", "vegetable oil", "neutral oil")

# Task D3's own explicit examples of a "pantry addition" that counts as optional even
# with no marker word in the ingredient line itself.
_OPTIONAL_PANTRY_SEASONING_PHRASES = (
    "pepper", "black pepper", "white pepper", "chilli", "chili", "chili flakes",
    "chilli flakes", "red pepper flakes",
)

_MAX_OPTIONAL_INGREDIENTS = 5

# Purely descriptive qualifiers that don't change an ingredient's core identity --
# stripped before comparing against the pantry/seasoning phrase lists above, so
# "coarse SEA salt" and "freshly ground black pepper" still reduce to "salt"/
# "black pepper" respectively. Deliberately does NOT include words that_would_ change
# identity if stripped (e.g. "garlic" in "garlic salt" stays, since garlic salt is a
# distinct seasoning blend, not plain table salt).
_QUALIFIER_WORDS = (
    "coarse", "sea", "kosher", "table", "fine", "freshly", "fresh", "cold", "warm",
    "extra", "virgin", "light", "neutral", "frying", "cooking", "vegetable", "ground",
)

_OPTIONAL_MARKER_RE = re.compile(
    r"\b(optional|if desired|to taste|for garnish|for serving|as needed|for topping)\b",
    re.IGNORECASE,
)

# Matches a leading quantity expression: a plain integer/decimal/range, a fraction, or
# a mixed number (checked in that preference order so "1 1/2 cups" captures the whole
# "1 1/2" rather than stopping at the bare "1"), optionally followed by a unit word.
# Known gap: an uncommon unit not in this list (e.g. "knob", "handful") is simply left
# as part of the name rather than the quantity -- a reasonable fallback, not a crash,
# and still produces a usable (if slightly over-inclusive) ingredient name.
_LEADING_QUANTITY_RE = re.compile(
    r"^(?P<qty>(?:\d+\s+\d+/\d+|\d+/\d+|\d+[\d.\-–]*)"
    r"(?:\s*(?:cups?|tbsp|tablespoons?|tsp|teaspoons?|lbs?|pounds?|oz|ounces?|g|grams?|"
    r"kg|kilograms?|ml|milliliters?|dl|deciliters?|l|liters?|cloves?|cans?|pieces?|"
    r"pinch(?:es)?|dash(?:es)?|slices?|stalks?|sprigs?|bunch(?:es)?|large|medium|small)\b)?)"
    r"\s*",
    re.IGNORECASE,
)

# A metric conversion in parentheses immediately after the quantity (e.g. "4 lbs
# (1.8 kg) pork belly") is part of the quantity, not the name -- distinguished from a
# *descriptive* parenthetical ("water (for the roasting pan)") by starting with a
# digit, which a conversion always does and a description never does.
_LEADING_CONVERSION_PAREN_RE = re.compile(r"^\(\s*\d[^)]*\)\s*")


def split_quantity_and_name(raw_line: str) -> Tuple[Optional[str], str]:
    """Splits one raw ingredient line into (quantity, name). Never returns an empty
    name -- a line that's entirely consumed by the quantity pattern (e.g. a bare
    number with no food word after it, which shouldn't happen in real data but must
    never crash or vanish a real line) falls back to (None, original_line)."""
    line = raw_line.strip()
    if not line:
        return None, line

    match = _LEADING_QUANTITY_RE.match(line)
    qty_parts: List[str] = []
    rest = line
    if match and match.group("qty").strip():
        qty_parts.append(match.group("qty").strip())
        rest = line[match.end():]

    conversion_match = _LEADING_CONVERSION_PAREN_RE.match(rest)
    if conversion_match:
        qty_parts.append(conversion_match.group(0).strip())
        rest = rest[conversion_match.end():]

    name = rest.strip()
    if not name:
        return None, line
    return (" ".join(qty_parts) if qty_parts else None), name


def _core_phrase(name: str) -> str:
    """Reduces an ingredient name to its comparable "core" for the pantry/seasoning
    phrase checks below: text before the first comma or parenthesis (dropping prep
    notes like ", plus more for the skin" or "(for the roasting pan)"), with purely
    descriptive qualifier words removed."""
    core = re.split(r"[,(]", name)[0].strip().lower()
    for qualifier in _QUALIFIER_WORDS:
        core = re.sub(rf"\b{qualifier}\b", "", core)
    return re.sub(r"\s+", " ", core).strip()


def is_pantry_basic(name: str) -> bool:
    return _core_phrase(name) in _PANTRY_BASIC_CORE_PHRASES


def is_optional_ingredient(raw_line: str, name: str) -> bool:
    if _OPTIONAL_MARKER_RE.search(raw_line):
        return True
    return _core_phrase(name) in _OPTIONAL_PANTRY_SEASONING_PHRASES


def structure_ingredients(raw_lines: List[str]) -> Dict[str, Any]:
    """Splits a recipe's raw ingredient lines into required/optional {name, quantity}
    pairs (Task D1/D2/D3), with assumed pantry basics filtered out of both (Task D5).
    See module docstring for the classification rules and their known limitations."""
    required: List[Dict[str, Optional[str]]] = []
    optional: List[Dict[str, Optional[str]]] = []

    for raw_line in raw_lines:
        if not raw_line or not raw_line.strip():
            continue
        quantity, name = split_quantity_and_name(raw_line)
        if is_pantry_basic(name):
            continue
        entry = {"name": name, "quantity": quantity}
        if is_optional_ingredient(raw_line, name) and len(optional) < _MAX_OPTIONAL_INGREDIENTS:
            optional.append(entry)
        else:
            required.append(entry)

    return {
        "required_ingredients": required,
        "optional_ingredients": optional,
        "pantry_basics_assumed": list(PANTRY_BASICS_NOTE),
    }

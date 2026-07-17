"""Tests for recipe_structuring.py -- Epic D's required/optional/pantry-basic split.
Test cases use real ingredient lines from the corpus (see src/notebooks/
synthetic_scandi_recipes.json's Ribbe recipe) alongside synthetic edge cases."""

from rag.recipe_structuring import (
    PANTRY_BASICS_NOTE,
    is_optional_ingredient,
    is_pantry_basic,
    split_quantity_and_name,
    structure_ingredients,
)


# ---------------------------------------------------------------------------
# split_quantity_and_name
# ---------------------------------------------------------------------------

def test_split_quantity_and_name_handles_a_unit_and_metric_conversion():
    """Real corpus line (Ribbe) -- the metric conversion is part of the quantity, not
    the name."""
    qty, name = split_quantity_and_name("4 lbs (1.8 kg) pork belly, skin on, ribs attached")
    assert qty == "4 lbs (1.8 kg)"
    assert name == "pork belly, skin on, ribs attached"


def test_split_quantity_and_name_keeps_a_descriptive_parenthetical_in_the_name():
    """Unlike a metric conversion, "(for the roasting pan)" describes the ingredient,
    not the quantity -- distinguished by not starting with a digit."""
    qty, name = split_quantity_and_name("1 cup water (for the roasting pan)")
    assert qty == "1 cup"
    assert name == "water (for the roasting pan)"


def test_split_quantity_and_name_handles_a_range_with_no_unit_word():
    qty, name = split_quantity_and_name("8-10 pitted prunes (optional, for the gravy)")
    assert qty == "8-10"
    assert name == "pitted prunes (optional, for the gravy)"


def test_split_quantity_and_name_handles_a_simple_unit():
    qty, name = split_quantity_and_name("2 tbsp flour")
    assert qty == "2 tbsp"
    assert name == "flour"


def test_split_quantity_and_name_handles_a_mixed_fraction():
    qty, name = split_quantity_and_name("1 1/2 cups flour")
    assert qty == "1 1/2 cups"
    assert name == "flour"


def test_split_quantity_and_name_handles_a_plain_fraction():
    qty, name = split_quantity_and_name("1/2 cup sugar")
    assert qty == "1/2 cup"
    assert name == "sugar"


def test_split_quantity_and_name_returns_none_quantity_when_there_is_none():
    qty, name = split_quantity_and_name("Salt and pepper to taste")
    assert qty is None
    assert name == "Salt and pepper to taste"


def test_split_quantity_and_name_never_returns_an_empty_name():
    qty, name = split_quantity_and_name("2")
    assert name == "2"


def test_split_quantity_and_name_handles_an_empty_line():
    assert split_quantity_and_name("") == (None, "")


# ---------------------------------------------------------------------------
# is_pantry_basic
# ---------------------------------------------------------------------------

def test_is_pantry_basic_matches_plain_water_salt_and_oil():
    assert is_pantry_basic("water") is True
    assert is_pantry_basic("salt") is True
    assert is_pantry_basic("cooking oil") is True
    assert is_pantry_basic("vegetable oil") is True


def test_is_pantry_basic_matches_qualified_salt_with_a_prep_note():
    """Real corpus line: "coarse sea salt, plus more for the skin" -- qualifiers and
    trailing prep notes must not prevent this from being recognized as plain salt."""
    assert is_pantry_basic("coarse sea salt, plus more for the skin") is True


def test_is_pantry_basic_does_not_match_a_distinct_seasoning_blend():
    """"garlic salt" is a specific named product, not plain table salt -- must not be
    silently hidden as an assumed pantry basic."""
    assert is_pantry_basic("garlic salt") is False


def test_is_pantry_basic_does_not_match_flavor_specific_oils():
    """Olive/sesame/coconut oil carry real dish-identity signal a generic "basic
    cooking oil" assumption doesn't -- only the two Task D5 explicitly names should be
    filtered."""
    assert is_pantry_basic("olive oil") is False
    assert is_pantry_basic("sesame oil") is False
    assert is_pantry_basic("coconut oil") is False


def test_is_pantry_basic_does_not_match_an_ordinary_ingredient():
    assert is_pantry_basic("chicken breast") is False
    assert is_pantry_basic("pan drippings") is False


# ---------------------------------------------------------------------------
# is_optional_ingredient
# ---------------------------------------------------------------------------

def test_is_optional_ingredient_detects_an_explicit_marker():
    assert is_optional_ingredient("8-10 pitted prunes (optional, for the gravy)", "pitted prunes (optional, for the gravy)") is True
    assert is_optional_ingredient("Fresh herbs for garnish", "Fresh herbs for garnish") is True
    assert is_optional_ingredient("Salt and pepper to taste", "Salt and pepper to taste") is True


def test_is_optional_ingredient_defaults_common_pantry_seasonings_to_optional():
    """Task D3's own explicit example: pepper/chilli count as optional even with no
    marker word in the line."""
    assert is_optional_ingredient("1 tsp freshly ground black pepper", "freshly ground black pepper") is True
    assert is_optional_ingredient("1 tsp chili flakes", "chili flakes") is True


def test_is_optional_ingredient_defaults_an_ordinary_ingredient_to_not_optional():
    assert is_optional_ingredient("2 chicken breasts", "chicken breasts") is False


# ---------------------------------------------------------------------------
# structure_ingredients
# ---------------------------------------------------------------------------

_RIBBE_INGREDIENTS = [
    "4 lbs (1.8 kg) pork belly, skin on, ribs attached",
    "2 tbsp coarse sea salt, plus more for the skin",
    "1 tsp freshly ground black pepper",
    "1 cup water (for the roasting pan)",
    "2 tbsp pan drippings",
    "2 tbsp flour",
    "2 cups beef or pork stock",
    "1 tbsp dark syrup or gravy browning (for color)",
    "8-10 pitted prunes (optional, for the gravy)",
]


def test_structure_ingredients_on_a_real_corpus_recipe():
    result = structure_ingredients(_RIBBE_INGREDIENTS)

    required_names = [i["name"] for i in result["required_ingredients"]]
    optional_names = [i["name"] for i in result["optional_ingredients"]]

    # Salt is filtered out entirely (pantry basic), water likewise.
    assert not any("salt" in n.lower() for n in required_names + optional_names)
    assert not any(n.lower().startswith("water") for n in required_names + optional_names)

    # Pepper and the explicitly-marked prunes are optional.
    assert any("pepper" in n.lower() for n in optional_names)
    assert any("prunes" in n.lower() for n in optional_names)

    # The core pork belly is required.
    assert any("pork belly" in n.lower() for n in required_names)

    # The always-shown pantry note is present regardless of what this recipe named.
    assert result["pantry_basics_assumed"] == list(PANTRY_BASICS_NOTE)


def test_structure_ingredients_caps_optional_at_five():
    lines = [f"1 tsp optional spice {i}" for i in range(8)]
    result = structure_ingredients(lines)

    assert len(result["optional_ingredients"]) == 5
    # Overflow beyond the cap is demoted back into required, never dropped.
    assert len(result["required_ingredients"]) == 3
    assert len(result["required_ingredients"]) + len(result["optional_ingredients"]) == 8


def test_structure_ingredients_skips_blank_lines():
    result = structure_ingredients(["2 eggs", "", "  ", "1 cup flour"])

    assert len(result["required_ingredients"]) == 2


def test_structure_ingredients_returns_the_pantry_note_even_with_no_pantry_items_present():
    result = structure_ingredients(["2 chicken breasts", "1 cup rice"])

    assert result["pantry_basics_assumed"] == list(PANTRY_BASICS_NOTE)
    assert len(result["required_ingredients"]) == 2

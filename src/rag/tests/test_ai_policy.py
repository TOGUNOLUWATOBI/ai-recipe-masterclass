"""Tests for ai_policy.py -- Epic G's shared everyday-meal generation policy."""

from rag.ai_policy import (
    FEW_SHOT_EXAMPLES,
    STRICT_RETRY_SUFFIX,
    build_meal_ideas_system_prompt,
    validate_generated_idea,
)


def _idea(**overrides):
    base = {
        "title": "Chicken and Rice",
        "selected_items_used": ["chicken fillet"],
        "required_ingredients": [{"name": "chicken fillet", "quantity": None}],
        "missing_required_ingredients": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# build_meal_ideas_system_prompt
# ---------------------------------------------------------------------------

def test_build_meal_ideas_system_prompt_includes_the_few_shot_examples():
    prompt = build_meal_ideas_system_prompt()
    assert FEW_SHOT_EXAMPLES in prompt


def test_build_meal_ideas_system_prompt_omits_the_strict_suffix_by_default():
    prompt = build_meal_ideas_system_prompt()
    assert STRICT_RETRY_SUFFIX not in prompt


def test_build_meal_ideas_system_prompt_includes_the_strict_suffix_on_retry():
    prompt = build_meal_ideas_system_prompt(strict_retry=True)
    assert STRICT_RETRY_SUFFIX in prompt


# ---------------------------------------------------------------------------
# validate_generated_idea (Task G4)
# ---------------------------------------------------------------------------

def test_validate_generated_idea_accepts_a_well_formed_idea():
    assert validate_generated_idea(_idea(), ["chicken fillet"]) is True


def test_validate_generated_idea_rejects_a_missing_title():
    assert validate_generated_idea(_idea(title=None), ["chicken fillet"]) is False


def test_validate_generated_idea_rejects_an_empty_title():
    assert validate_generated_idea(_idea(title=""), ["chicken fillet"]) is False


def test_validate_generated_idea_rejects_empty_required_ingredients():
    assert validate_generated_idea(_idea(required_ingredients=[]), ["chicken fillet"]) is False


def test_validate_generated_idea_rejects_an_ingredient_listed_as_both_used_and_missing():
    idea = _idea(selected_items_used=["chicken fillet"], missing_required_ingredients=["chicken fillet"])
    assert validate_generated_idea(idea, ["chicken fillet"]) is False


def test_validate_generated_idea_rejects_a_hallucinated_used_ingredient():
    """selected_items_used must only ever contain names that were actually in the
    given cart/store list -- never something the model introduced on its own."""
    idea = _idea(selected_items_used=["chicken fillet", "truffle oil"])
    assert validate_generated_idea(idea, ["chicken fillet"]) is False

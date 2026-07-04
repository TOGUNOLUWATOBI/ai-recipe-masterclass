"""Tests for recipe_loader.py — focused on the exact bugs found this session:
dedup must remove byte-identical duplicates but NOT merge different recipes that
happen to share a title (hundreds of real recipes do)."""

import json

from rag.recipe_loader import _dedupe_exact, _format_recipe_text, load_recipe_sources


def test_format_recipe_text_matches_training_format():
    recipe = {"title": "Jollof Rice", "ingredients": ["rice", "tomato"], "instructions": ["Cook.", "Serve."]}
    text = _format_recipe_text(recipe)
    assert text == "### Jollof Rice\n\n**Ingredients:**\nrice, tomato\n\n**Instructions:**\nCook. Serve."


def test_load_recipe_sources_skips_malformed_entries(tmp_path):
    path = tmp_path / "recipes.json"
    path.write_text(json.dumps([
        {"title": "Valid Recipe", "ingredients": ["egg"], "instructions": ["Cook."]},
        {"title": "Missing Ingredients", "instructions": ["Cook."]},
        {"title": "Missing Instructions", "ingredients": ["egg"]},
        {},
    ]))

    chunks = load_recipe_sources([path])

    assert len(chunks) == 1
    assert chunks[0]["title"] == "Valid Recipe"


def test_load_recipe_sources_preserves_extra_fields_as_metadata(tmp_path):
    path = tmp_path / "recipes.json"
    path.write_text(json.dumps([
        {"title": "Jollof Rice", "ingredients": ["rice"], "instructions": ["Cook."],
         "country": "Nigeria", "african_region": "West Africa"},
    ]))

    chunks = load_recipe_sources([path])

    assert chunks[0]["metadata"] == {"country": "Nigeria", "african_region": "West Africa"}


def test_dedupe_exact_removes_byte_identical_duplicates():
    chunks = [
        {"text": "### Carrot Cake\n\nA", "source_file": "a.json", "chunk_id": 0},
        {"text": "### Carrot Cake\n\nA", "source_file": "b.json", "chunk_id": 0},  # exact duplicate
    ]

    deduped = _dedupe_exact(chunks)

    assert len(deduped) == 1


def test_dedupe_exact_keeps_same_title_different_content():
    """The bug this guards against: hundreds of real recipes share a title (many
    different "Carrot Cake" recipes) with genuinely different ingredients/instructions.
    Deduping by title alone would silently discard real, distinct recipes."""
    chunks = [
        {"text": "### Carrot Cake\n\nRecipe A ingredients", "source_file": "a.json", "chunk_id": 0},
        {"text": "### Carrot Cake\n\nRecipe B ingredients (completely different)", "source_file": "b.json", "chunk_id": 0},
    ]

    deduped = _dedupe_exact(chunks)

    assert len(deduped) == 2

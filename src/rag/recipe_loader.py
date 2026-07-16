
"""Loads curated recipe JSON files into the flat chunk format the pipeline expects.

One recipe = one chunk. Recipes are short and self-contained, so unlike PDF chunking
(fixed/sliding/semantic strategies), there's no benefit to splitting a recipe apart —
ingredients and instructions always need to stay together for a coherent answer.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .country_demonyms import demonym_for

logger = logging.getLogger(__name__)


def _format_recipe_text(recipe: Dict[str, Any]) -> str:
    """Match the exact formatting the fine-tuned model was trained on, so retrieved
    context looks like what the model already expects rather than a foreign format.

    Includes country/region/demonym (when present) — found this session because
    "nigerian stew" surfaced a Malian recipe instead of the corpus's own "Obe Ata (stew)".
    Two layered bugs: (1) country was only ever kept in metadata, never in the embedded/
    BM25 text, so a query naming the country had zero lexical signal; (2) even after
    adding "Nigeria" to the text, BM25 does no stemming, so a query for "nigerian" still
    shared no token with "Nigeria" (confirmed empirically — Obe Ata's BM25 score for that
    query came entirely from the word "stew", ranking 110th, outside the candidate pool).
    Adding the demonym form (see country_demonyms.py) alongside the country name closes
    that gap directly instead of relying on a generic stemmer, which wouldn't relate
    "Nigeria"/"Nigerian" or "Mali"/"Malian" anyway. Harmless no-op for
    web_recipe_corpus.json entries, which don't have these fields at all."""
    title = recipe["title"]
    ingredients = ", ".join(recipe["ingredients"])
    instructions = " ".join(recipe["instructions"])
    country = recipe.get("country")
    origin_bits = [v for v in (country, demonym_for(country) if country else None,
                                recipe.get("region"), recipe.get("african_region")) if v]
    origin_line = f"**Origin:** {', '.join(dict.fromkeys(origin_bits))}\n\n" if origin_bits else ""
    return f"### {title}\n\n{origin_line}**Ingredients:**\n{ingredients}\n\n**Instructions:**\n{instructions}"


def load_recipe_sources(paths: List[Path]) -> List[Dict[str, Any]]:
    """Load one or more recipe JSON files into a flat list of chunk dicts.

    Each source file must be a JSON array of objects with at least:
      - title: str
      - ingredients: list[str]
      - instructions: list[str]
    Any extra fields (country, african_region, etc.) are preserved under 'metadata'.

    Returns chunk dicts with: text, char_len, source_file, chunk_id, title, ingredients,
    instructions. ingredients/instructions are kept as the original structured lists
    (not just flattened into `text`) so downstream consumers -- meal_ideas.py's
    ingredient-coverage matching (Epic C4) -- can work against real per-recipe
    ingredient lines instead of re-parsing a comma-joined blob back apart, which is
    lossy (individual ingredient lines routinely contain their own internal commas,
    e.g. "4 lbs (1.8 kg) pork belly, skin on, ribs attached").
    """
    chunks: List[Dict[str, Any]] = []

    for path in paths:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Recipe source not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            recipes = json.load(f)

        logger.info(f"Loading {len(recipes)} recipes from {path.name}")

        for i, recipe in enumerate(recipes):
            if not (recipe.get("title") and recipe.get("ingredients") and recipe.get("instructions")):
                logger.warning(f"Skipping malformed recipe at {path.name}[{i}]: missing title/ingredients/instructions")
                continue

            text = _format_recipe_text(recipe)
            known_fields = {"title", "ingredients", "instructions"}
            metadata = {k: v for k, v in recipe.items() if k not in known_fields}

            chunks.append({
                "text": text,
                "char_len": len(text),
                # Full path, not just the basename -- this is the uniqueness half of
                # pipeline.py's stable point-ID derivation (source_file + chunk_id),
                # and chunk_id only resets to 0 per-file, so two files sharing a bare
                # filename in different directories would otherwise collide on the
                # same point ID and silently drop one recipe from the index.
                "source_file": str(path),
                "chunk_id": i,
                "title": recipe["title"],
                "ingredients": recipe["ingredients"],
                "instructions": recipe["instructions"],
                "metadata": metadata,
            })

    chunks = _dedupe_exact(chunks)
    logger.info(f"Loaded {len(chunks)} total recipe chunks from {len(paths)} source file(s)")
    return chunks


def _dedupe_exact(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop only byte-identical (title+ingredients+instructions) duplicates — e.g. the same
    recipe appearing in both food.com and kaggle. Deliberately does NOT dedupe by title alone:
    hundreds of recipes share a common name (many different "Carrot Cake" or "Manhattan"
    recipes) with genuinely different ingredients/instructions — those are real variety, not
    redundancy, and merging them would silently throw away legitimate recipes."""
    seen = set()
    deduped = []
    for chunk in chunks:
        if chunk["text"] not in seen:
            seen.add(chunk["text"])
            deduped.append(chunk)

    removed = len(chunks) - len(deduped)
    if removed:
        logger.info(f"Removed {removed} exact-duplicate recipe(s) (identical title+ingredients+instructions)")
    return deduped


def print_recipe_statistics(chunks: List[Dict[str, Any]]) -> None:
    if not chunks:
        print("No recipe chunks loaded.")
        return

    total_chars = sum(c["char_len"] for c in chunks)
    # Display just the basenames -- source_file itself is the full path (needed for
    # point-ID uniqueness, see load_recipe_sources()), which would make this summary
    # noisy since every entry shares the same directory prefix.
    sources = sorted({Path(c["source_file"]).name for c in chunks})

    print("\n" + "=" * 80)
    print("RECIPE CHUNK STATISTICS")
    print("=" * 80)
    print(f"Total recipes: {len(chunks):,}")
    print(f"Average length: {total_chars / len(chunks):.0f} characters")
    print(f"Source files: {sources}")
    print("=" * 80 + "\n")

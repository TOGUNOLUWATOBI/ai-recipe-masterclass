"""Builds a large recipe JSON corpus from food.com + kaggle for RAG retrieval —
separate from cluster_finetuner.py's use of the same datasets for fine-tuning.

Key difference from cluster_finetuner.py's clean_field(): that function flattens
ingredients/instructions into a single joined string for training text. This script
keeps them as proper lists, matching synthetic_african_recipes.json's schema, since
recipe_loader.py's ", ".join(recipe["ingredients"]) would silently iterate
character-by-character if given a flat string instead of a list.

Usage:
    cd "AI Recipe Masterclass/src" && python3 -m rag.build_recipe_corpus
"""

import argparse
import ast
import json
import logging
import re
from pathlib import Path

from datasets import load_dataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "notebooks" / "web_recipe_corpus.json"


def parse_r_vector(raw) -> list:
    """Parse R's c("a", "b", "c") vector-as-string format (food.com)."""
    if not raw:
        return []
    return re.findall(r'"([^"]*)"', str(raw))


def parse_py_list(raw) -> list:
    """Parse Python's ['a', 'b', 'c'] list-as-string format (kaggle)."""
    if not raw:
        return []
    try:
        parsed = ast.literal_eval(raw)
        return list(parsed) if isinstance(parsed, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return []


def build_foodcom_recipes(min_rating: float, min_reviews: int) -> list:
    """food.com: RecipeIngredientParts (names) and RecipeIngredientQuantities (amounts)
    are separate parallel R-vectors — zip them together for real ingredient lines
    ("4 blueberries") instead of just bare ingredient names."""
    logger.info("Loading food.com...")
    dataset = load_dataset("AkashPS11/recipes_data_food.com", split="train")

    recipes = []
    for row in dataset:
        title = row.get("Name")
        names = parse_r_vector(row.get("RecipeIngredientParts"))
        quantities = parse_r_vector(row.get("RecipeIngredientQuantities"))
        instructions = parse_r_vector(row.get("RecipeInstructions"))

        if not (title and names and instructions):
            continue

        rating = row.get("AggregatedRating") or 0
        reviews = row.get("ReviewCount") or 0
        if rating < min_rating or reviews < min_reviews:
            continue

        ingredients = [
            f"{qty} {name}".strip() if qty and qty.upper() != "NA" else name
            for name, qty in zip(names, quantities + [""] * (len(names) - len(quantities)))
        ]

        if len(" ".join(instructions)) < 20:
            continue

        recipes.append({
            "title": title,
            "source": "food.com",
            "ingredients": ingredients,
            "instructions": instructions,
        })

    logger.info(f"food.com: kept {len(recipes)} recipes (rating>={min_rating}, reviews>={min_reviews})")
    return recipes


def build_kaggle_recipes() -> list:
    logger.info("Loading kaggle food recipes...")
    dataset = load_dataset("Hieu-Pham/kaggle_food_recipes", split="train")

    recipes = []
    for row in dataset:
        title = row.get("Title")
        ingredients = parse_py_list(row.get("Cleaned_Ingredients")) or parse_py_list(row.get("Ingredients"))
        raw_instructions = row.get("Instructions") or ""
        instructions = [s.strip() for s in raw_instructions.split("\n") if s.strip()]

        if not (title and ingredients and instructions):
            continue
        if len(" ".join(instructions)) < 20:
            continue

        recipes.append({
            "title": title,
            "source": "kaggle",
            "ingredients": ingredients,
            "instructions": instructions,
        })

    logger.info(f"kaggle: kept {len(recipes)} recipes")
    return recipes


def build_indian_recipes() -> list:
    """Text-sourced Indian recipes (from archanaskitchen.com via this HF mirror) — fills
    the gap food.com/kaggle leave almost entirely empty for Indian cuisine (biryani etc.)."""
    logger.info("Loading Indian recipes...")
    dataset = load_dataset("Anupam007/indian-recipe-dataset", split="train")

    recipes = []
    for row in dataset:
        title = row.get("TranslatedRecipeName")
        raw_ingredients = row.get("TranslatedIngredients") or ""
        ingredients = [s.strip() for s in raw_ingredients.split(",") if s.strip()]
        raw_instructions = row.get("TranslatedInstructions") or ""
        instructions = [s.strip() for s in raw_instructions.split("\n") if s.strip()]

        if not (title and ingredients and instructions):
            continue
        if len(" ".join(instructions)) < 20:
            continue

        recipes.append({
            "title": title,
            "source": "indian-recipe-dataset",
            "cuisine": row.get("Cuisine"),
            "ingredients": ingredients,
            "instructions": instructions,
        })

    logger.info(f"Indian recipes: kept {len(recipes)}")
    return recipes


def main():
    parser = argparse.ArgumentParser(description="Build a large recipe JSON corpus for RAG")
    parser.add_argument("--min-rating", type=float, default=4.0, help="Minimum food.com AggregatedRating to include")
    parser.add_argument("--min-reviews", type=int, default=3, help="Minimum food.com ReviewCount to include")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    recipes = (
        build_foodcom_recipes(args.min_rating, args.min_reviews)
        + build_kaggle_recipes()
        + build_indian_recipes()
    )
    logger.info(f"Total: {len(recipes)} recipes")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False)

    logger.info(f"Wrote {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

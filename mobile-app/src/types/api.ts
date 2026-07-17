/**
 * Types mirroring src/rag/pipeline_server.py's actual response shapes. Kept in one
 * file, hand-synced with the backend rather than generated — the API surface is small
 * (3 endpoints) and stable enough that a codegen step would add more overhead than it
 * saves.
 */

export interface RetrievedRecipe {
  id: number;
  score: number;
  payload: {
    title?: string;
    text?: string;
    source_file?: string;
    chunk_id?: number;
  };
  text: string;
  dense_score?: number;
  rerank_score?: number;
}

export interface QueryResponse {
  question: string;
  retrieved: RetrievedRecipe[];
  grounded: RetrievedRecipe[];
  context: string;
  answer: string | null;
  error: string | null;
  elapsed: number;
}

export interface GeneratedRecipe {
  title: string | null;
  text: string;
  rerank_score: number | null;
  dense_score: number | null;
}

export type RecipeSource = "corpus" | "generated" | null;

export interface IngredientsResponse {
  ingredients: string[];
  source: RecipeSource;
  count: number;
  recipes: GeneratedRecipe[];
  generated: string | null;
  error: string | null;
}

// Coarse label derived from the richer Epic A classification below (see the backend's
// product_classification.legacy_category()) -- "non_food" items (soap, batteries, ...)
// and "snack" items (candy, chips, soda, ready meals, ...) are still returned alongside
// "main_food", just excluded from the ingredient list the backend feeds into recipe
// generation. Optional/nullable so older cached rows (pre-category) don't break callers
// that don't care about it.
export type DiscountedProductCategory = "main_food" | "snack" | "non_food";

// Epic A's richer classification -- not yet consumed by any screen (that's Epic B/C/E
// territory), added here purely so this file stays hand-synced with the backend's
// actual response shape. See src/rag/product_classification.py for what each value
// means; `recipe_eligible` is what /recipes/discounted now gates recipe generation on,
// replacing the old `category === "main_food"` check.
export type ShoppingGroup = "food" | "non_food";
export type FoodUsageClass =
  | "primary_ingredient"
  | "supporting_ingredient"
  | "ready_meal"
  | "ready_to_eat"
  | "beverage"
  | "snack_or_treat"
  | "unknown"
  | "not_applicable";
export type MealRole =
  | "protein"
  | "carbohydrate"
  | "vegetable"
  | "fruit"
  | "dairy"
  | "pantry"
  | "sauce_or_condiment"
  | "bread_or_bakery"
  | "other"
  | "not_applicable";

export interface DiscountedProduct {
  product_name: string;
  category: DiscountedProductCategory | null;
  // Optional (not just nullable) even though the live backend always sends these now --
  // keeping them optional means the many existing test fixtures/mocks built before
  // Epic A don't all need to be touched just to satisfy the type checker. A missing key
  // here should be treated exactly like an explicit null (see cart/cartItemId.ts and
  // CartContext.tsx's "?? " fallbacks).
  shopping_group?: ShoppingGroup | null;
  food_usage_class?: FoodUsageClass | null;
  meal_role?: MealRole | null;
  recipe_eligible?: boolean | null;
  recipe_exclusion_reason?: string | null;
  current_price: number;
  // null when we don't have enough price history to compute a meaningful discount —
  // the backend now returns every product per store, not just confirmed discounts, so
  // these are absent far more often than they used to be. Render a discount badge only
  // when both are present.
  reference_price: number | null;
  discount_pct: number | null;
  unit_price: number | null;
  // The quantity basis unit_price is expressed against -- 'kg', 'L', or 'pc' -- since it
  // varies per product (see grocery_discounts.py's _compute_unit_price()). Null exactly
  // when unit_price is null.
  unit_price_unit: string | null;
  image_url: string | null;
  store_name: string | null;
  store_logo_url: string | null;
}

export interface DiscountedResponse {
  discounted_ingredients: DiscountedProduct[];
  source: RecipeSource;
  count: number;
  recipes: GeneratedRecipe[];
  generated: string | null;
  error: string | null;
  updated_at: string | null;
}

// Epic E: mirrors rag/meal_ideas.py's response shape for both /meal-ideas/from-cart
// (Epic C) and /meal-ideas/from-store (Epic E) -- same MealIdea shape either way, just
// a different excluded-items field name and, for the store flow, an echoed store_name.
// Distinct from RecipeSource ("corpus"/"generated") -- meal_ideas.py's own vocabulary
// is "retrieved"/"generated" (see _generate_ideas_from_eligible_rows()).
export type MealIdeaSource = "retrieved" | "generated" | null;

export type CompletionStatus = "complete" | "nearly_complete" | "partial";

export interface StructuredIngredient {
  name: string;
  // null when recipe_structuring.py's split_quantity_and_name() found no leading
  // quantity/unit on the raw ingredient line (e.g. "salt to taste").
  quantity: string | null;
}

export interface MealIdea {
  title: string | null;
  description: string | null;
  servings: number | null;
  completion_status: CompletionStatus;
  selected_items_used: string[];
  required_ingredients: StructuredIngredient[];
  optional_ingredients: StructuredIngredient[];
  missing_required_ingredients: string[];
  ingredient_coverage_percentage: number;
  pantry_basics_assumed: string[];
  estimated_complexity: string | null;
  source_type: "retrieved" | "generated";
}

export interface ExcludedItem {
  product_name: string;
  reason: string;
}

export interface MealIdeasFromCartResponse {
  ideas: MealIdea[];
  excluded_cart_items: ExcludedItem[];
  source: MealIdeaSource;
}

export interface MealIdeasFromStoreResponse {
  ideas: MealIdea[];
  excluded_store_items: ExcludedItem[];
  store_name: string;
  source: MealIdeaSource;
}

// Epic F: mirrors rag/ingredient_index.py's match_ingredient_offers() output --
// POST /ingredient-offers returns these for each requested ingredient name, read from
// the precomputed discount_ingredient_index (never a live scan/LLM call, Task F3).
export type MatchConfidence = "exact" | "alias" | "fuzzy";

export interface IngredientOffer {
  normalized_ingredient_key: string;
  ingredient_aliases: string[];
  original_product_name: string;
  store_name: string | null;
  current_price: number | null;
  reference_price: number | null;
  discount_pct: number | null;
  unit_price: number | null;
  unit_price_unit: string | null;
  image_url: string | null;
  store_logo_url: string | null;
  // The flyer's own real validity window (grocery_discounts.py's run_from/run_till) --
  // null for an older cached row written before Epic F1 carried these through.
  valid_from: string | null;
  valid_until: string | null;
  shopping_group: ShoppingGroup | null;
  food_usage_class: FoodUsageClass | null;
  meal_role: MealRole | null;
  recipe_eligible: boolean;
  snapshot_id: string | null;
  updated_at: string | null;
  // exact/alias/fuzzy (Task F7) -- a caller should hide or visibly label a "fuzzy"
  // match rather than presenting it with the same trust as an exact/alias one.
  match_confidence: MatchConfidence;
}

export interface IngredientOffersResponse {
  snapshot_updated_at: string | null;
  ingredients: { ingredient: string; offers: IngredientOffer[] }[];
}

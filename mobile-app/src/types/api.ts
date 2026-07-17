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
  // here should be treated exactly like an explicit null.
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

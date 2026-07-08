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

export interface DiscountedProduct {
  category: string;
  product_name: string;
  current_price: number;
  // null when we don't have enough price history to compute a meaningful discount —
  // the backend now returns every product per store, not just confirmed discounts, so
  // these are absent far more often than they used to be. Render a discount badge only
  // when both are present.
  reference_price: number | null;
  discount_pct: number | null;
  unit_price: number | null;
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

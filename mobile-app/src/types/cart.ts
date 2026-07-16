import type { DiscountedProduct, FoodUsageClass, MealRole, ShoppingGroup } from "./api";

/**
 * One line item in the shopping cart (Epic B). Persisted to AsyncStorage as a plain
 * JSON array -- see CartContext.tsx. Snapshotted from a DiscountedProduct at the
 * moment it's added rather than re-read live, since the discount it came from can
 * expire or drop out of the next scan entirely (see CartScreen's expiry check) -- the
 * cart should still show what the user saw when they added it.
 */
export interface CartItem {
  cart_item_id: string;
  discount_item_id: string;
  product_name: string;
  // Client-side approximation only (lowercased/trimmed) -- the backend's real
  // ingredient normalization (grocery_terms.py) is Norwegian-flyer-heading-specific
  // and only ever runs server-side; this field exists purely so the cart's own data
  // shape matches the change spec, not to replicate that logic here.
  normalized_product_name: string;
  store_name: string | null;
  current_price: number;
  reference_price: number | null;
  image_url: string | null;
  shopping_group: ShoppingGroup | null;
  food_usage_class: FoodUsageClass | null;
  meal_role: MealRole | null;
  recipe_eligible: boolean | null;
  quantity: number;
  added_at: string; // ISO 8601
  // Selection state for meal-idea generation (Epic C/E consume this later) -- only
  // ever true for a recipe_eligible item; see CartContext.addItem()/toggleMealIdeaSelection().
  selected_for_meal_ideas: boolean;
}

/**
 * Stable-enough key for "the same product from the same store" -- the backend has no
 * durable per-offer ID today (DiscountedProduct carries no id field at all), so this
 * is a deliberate, documented approximation: (store_name, product_name) is unique
 * within one discount scan in practice, which is all the cart needs for
 * add-again-increments-quantity (Epic B5) and matching against the latest snapshot
 * for expiry detection (Epic B6) to work. Exported so CartContext and
 * AddToCartButton derive the same key rather than duplicating this logic.
 */
export function cartItemIdFor(deal: Pick<DiscountedProduct, "product_name" | "store_name">): string {
  return `${deal.store_name ?? "unknown-store"}::${deal.product_name}`;
}

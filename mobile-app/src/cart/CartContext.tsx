import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { DiscountedProduct } from "../types/api";
import { cartItemIdFor, type CartItem } from "../types/cart";

const STORAGE_KEY = "cart";

interface CartContextValue {
  items: CartItem[];
  foodItems: CartItem[];
  nonFoodItems: CartItem[];
  mealIdeaSelectedCount: number;
  getQuantity: (deal: Pick<DiscountedProduct, "product_name" | "store_name">) => number;
  // Needs the full deal, not just an id: the item may not exist in the cart yet, in
  // which case a fresh CartItem is built from it. Used by AddToCartButton (DealCard/
  // DealDetailScreen), where the live DiscountedProduct is always on hand.
  addItem: (deal: DiscountedProduct) => void;
  // Adjusts a line already known to be in the cart -- no deal data needed. Used by
  // AddToCartButton once quantity > 0, and by CartScreen's own stepper (which only
  // ever has CartItem data, not a live DiscountedProduct, to work with).
  incrementQuantity: (cartItemId: string) => void;
  decrementQuantity: (cartItemId: string) => void;
  removeItem: (cartItemId: string) => void;
  toggleMealIdeaSelection: (cartItemId: string) => void;
  clearCart: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  // Guards the persistence effect below from firing with the initial empty array
  // before the AsyncStorage read has had a chance to resolve and populate real data --
  // without this, a real persisted cart would get silently overwritten with [] on
  // every fresh app launch.
  const isHydrated = useRef(false);

  // Loads the persisted cart once on mount -- a fresh install (or a read/parse
  // failure) just keeps the empty cart this component already started with.
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (!stored) return;
        try {
          const parsed = JSON.parse(stored);
          if (Array.isArray(parsed)) {
            setItems(parsed);
          }
        } catch {
          // Corrupt persisted value -- ignore, keep the empty cart.
        }
      })
      .catch(() => {
        // Ignore -- falls back to an empty cart, same as a fresh install.
      })
      .finally(() => {
        isHydrated.current = true;
      });
  }, []);

  useEffect(() => {
    if (!isHydrated.current) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items)).catch(() => {
      // Best-effort persistence -- the cart still works for the rest of this session
      // even if the write fails, it just won't survive an app restart.
    });
  }, [items]);

  const addItem = useCallback((deal: DiscountedProduct) => {
    const id = cartItemIdFor(deal);
    setItems((prev) => {
      const existing = prev.find((item) => item.cart_item_id === id);
      if (existing) {
        // Epic B5: adding an already-present product increases its quantity instead
        // of creating a second identical row.
        return prev.map((item) => (item.cart_item_id === id ? { ...item, quantity: item.quantity + 1 } : item));
      }
      const newItem: CartItem = {
        cart_item_id: id,
        discount_item_id: id,
        product_name: deal.product_name,
        normalized_product_name: deal.product_name.trim().toLowerCase(),
        store_name: deal.store_name,
        current_price: deal.current_price,
        reference_price: deal.reference_price,
        image_url: deal.image_url,
        shopping_group: deal.shopping_group ?? null,
        food_usage_class: deal.food_usage_class ?? null,
        meal_role: deal.meal_role ?? null,
        recipe_eligible: deal.recipe_eligible ?? null,
        quantity: 1,
        added_at: new Date().toISOString(),
        // Eligible items start selected by default -- the common case is "yes, use
        // this in meal ideas" (Epic B4), and the user opts individual items out
        // rather than having to opt every item in.
        selected_for_meal_ideas: deal.recipe_eligible === true,
      };
      return [...prev, newItem];
    });
  }, []);

  const incrementQuantity = useCallback((cartItemId: string) => {
    setItems((prev) =>
      prev.map((item) => (item.cart_item_id === cartItemId ? { ...item, quantity: item.quantity + 1 } : item))
    );
  }, []);

  const decrementQuantity = useCallback((cartItemId: string) => {
    setItems((prev) =>
      prev
        .map((item) => (item.cart_item_id === cartItemId ? { ...item, quantity: item.quantity - 1 } : item))
        // Epic B5: quantity reaching zero removes the row.
        .filter((item) => item.quantity > 0)
    );
  }, []);

  const removeItem = useCallback((cartItemId: string) => {
    setItems((prev) => prev.filter((item) => item.cart_item_id !== cartItemId));
  }, []);

  const toggleMealIdeaSelection = useCallback((cartItemId: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.cart_item_id === cartItemId && item.recipe_eligible
          ? { ...item, selected_for_meal_ideas: !item.selected_for_meal_ideas }
          : item
      )
    );
  }, []);

  const clearCart = useCallback(() => setItems([]), []);

  const getQuantity = useCallback(
    (deal: Pick<DiscountedProduct, "product_name" | "store_name">) => {
      const id = cartItemIdFor(deal);
      return items.find((item) => item.cart_item_id === id)?.quantity ?? 0;
    },
    [items]
  );

  // A missing/null shopping_group (an older cached item, or a fixture that predates
  // Epic A) defaults to "food" -- same fallback convention StoresScreen/
  // StoreItemsScreen already use for the legacy category field.
  const foodItems = useMemo(() => items.filter((item) => (item.shopping_group ?? "food") !== "non_food"), [items]);
  const nonFoodItems = useMemo(() => items.filter((item) => (item.shopping_group ?? "food") === "non_food"), [items]);
  const mealIdeaSelectedCount = useMemo(
    () => items.filter((item) => item.recipe_eligible && item.selected_for_meal_ideas).length,
    [items]
  );

  const value = useMemo<CartContextValue>(
    () => ({
      items,
      foodItems,
      nonFoodItems,
      mealIdeaSelectedCount,
      getQuantity,
      addItem,
      incrementQuantity,
      decrementQuantity,
      removeItem,
      toggleMealIdeaSelection,
      clearCart,
    }),
    [
      items,
      foodItems,
      nonFoodItems,
      mealIdeaSelectedCount,
      getQuantity,
      addItem,
      incrementQuantity,
      decrementQuantity,
      removeItem,
      toggleMealIdeaSelection,
      clearCart,
    ]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error("useCart() must be called within a CartProvider");
  }
  return context;
}

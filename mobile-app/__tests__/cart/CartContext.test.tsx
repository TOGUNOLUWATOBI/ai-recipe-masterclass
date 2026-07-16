import AsyncStorage from "@react-native-async-storage/async-storage";
import { render, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Text, TouchableOpacity } from "react-native";
import { CartProvider, useCart } from "../../src/cart/CartContext";
import type { DiscountedProduct } from "../../src/types/api";

const ELIGIBLE_DEAL: DiscountedProduct = {
  product_name: "Kyllingfilet",
  category: "main_food",
  current_price: 80,
  reference_price: null,
  discount_pct: null,
  unit_price: null,
  unit_price_unit: null,
  image_url: null,
  store_name: "Kiwi",
  store_logo_url: null,
  shopping_group: "food",
  food_usage_class: "primary_ingredient",
  meal_role: "protein",
  recipe_eligible: true,
};

const INELIGIBLE_DEAL: DiscountedProduct = {
  ...ELIGIBLE_DEAL,
  product_name: "Coca-Cola",
  category: "snack",
  shopping_group: "food",
  food_usage_class: "beverage",
  meal_role: "not_applicable",
  recipe_eligible: false,
};

const NON_FOOD_DEAL: DiscountedProduct = {
  ...ELIGIBLE_DEAL,
  product_name: "Toalettpapir",
  category: "non_food",
  shopping_group: "non_food",
  food_usage_class: "not_applicable",
  meal_role: "not_applicable",
  recipe_eligible: false,
};

function Probe() {
  const cart = useCart();
  return (
    <>
      <Text testID="item-count">{cart.items.length}</Text>
      <Text testID="food-count">{cart.foodItems.length}</Text>
      <Text testID="non-food-count">{cart.nonFoodItems.length}</Text>
      <Text testID="selected-count">{cart.mealIdeaSelectedCount}</Text>
      <Text testID="eligible-quantity">{cart.getQuantity(ELIGIBLE_DEAL)}</Text>
      <TouchableOpacity testID="add-eligible" onPress={() => cart.addItem(ELIGIBLE_DEAL)}>
        <Text>add eligible</Text>
      </TouchableOpacity>
      <TouchableOpacity testID="add-ineligible" onPress={() => cart.addItem(INELIGIBLE_DEAL)}>
        <Text>add ineligible</Text>
      </TouchableOpacity>
      <TouchableOpacity testID="add-non-food" onPress={() => cart.addItem(NON_FOOD_DEAL)}>
        <Text>add non-food</Text>
      </TouchableOpacity>
      <TouchableOpacity testID="clear" onPress={cart.clearCart}>
        <Text>clear</Text>
      </TouchableOpacity>
      {cart.items.map((item) => (
        <React.Fragment key={item.cart_item_id}>
          <Text testID={`qty-${item.cart_item_id}`}>{item.quantity}</Text>
          <Text testID={`selected-${item.cart_item_id}`}>{String(item.selected_for_meal_ideas)}</Text>
          <TouchableOpacity
            testID={`decrement-${item.cart_item_id}`}
            onPress={() => cart.decrementQuantity(item.cart_item_id)}
          >
            <Text>-</Text>
          </TouchableOpacity>
          <TouchableOpacity
            testID={`increment-${item.cart_item_id}`}
            onPress={() => cart.incrementQuantity(item.cart_item_id)}
          >
            <Text>+</Text>
          </TouchableOpacity>
          <TouchableOpacity testID={`remove-${item.cart_item_id}`} onPress={() => cart.removeItem(item.cart_item_id)}>
            <Text>remove</Text>
          </TouchableOpacity>
          <TouchableOpacity
            testID={`toggle-${item.cart_item_id}`}
            onPress={() => cart.toggleMealIdeaSelection(item.cart_item_id)}
          >
            <Text>toggle</Text>
          </TouchableOpacity>
        </React.Fragment>
      ))}
    </>
  );
}

class CaughtErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return <Text testID="caught-error">{this.state.error.message}</Text>;
    }
    return this.props.children;
  }
}

async function renderProbe() {
  return render(
    <CartProvider>
      <Probe />
    </CartProvider>
  );
}

describe("CartContext", () => {
  afterEach(async () => {
    await AsyncStorage.clear();
  });

  it("useCart() throws when called outside a CartProvider", async () => {
    const originalConsoleError = console.error;
    console.error = jest.fn();
    try {
      await render(
        <CaughtErrorBoundary>
          <Probe />
        </CaughtErrorBoundary>
      );
      expect(screen.getByTestId("caught-error").props.children).toBe("useCart() must be called within a CartProvider");
    } finally {
      console.error = originalConsoleError;
    }
  });

  it("starts with an empty cart", async () => {
    await renderProbe();
    expect(screen.getByTestId("item-count").props.children).toBe(0);
  });

  it("addItem adds a new line with quantity 1", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("add-eligible"));

    expect(screen.getByTestId("item-count").props.children).toBe(1);
    expect(screen.getByTestId("eligible-quantity").props.children).toBe(1);
  });

  it("adding the same product again increases quantity instead of duplicating the row (Epic B5)", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("add-eligible"));

    expect(screen.getByTestId("item-count").props.children).toBe(1);
    expect(screen.getByTestId("eligible-quantity").props.children).toBe(2);
  });

  it("defaults an eligible item to selected for meal ideas, and an ineligible item to not selected", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("add-ineligible"));

    const eligibleId = "Kiwi::Kyllingfilet";
    const ineligibleId = "Kiwi::Coca-Cola";
    expect(screen.getByTestId(`selected-${eligibleId}`).props.children).toBe("true");
    expect(screen.getByTestId(`selected-${ineligibleId}`).props.children).toBe("false");
  });

  it("incrementQuantity increases an existing line's quantity", async () => {
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("add-eligible"));

    await user.press(screen.getByTestId("increment-Kiwi::Kyllingfilet"));

    expect(screen.getByTestId("qty-Kiwi::Kyllingfilet").props.children).toBe(2);
  });

  it("decrementQuantity decreases quantity and removes the line at zero (Epic B5)", async () => {
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("increment-Kiwi::Kyllingfilet"));

    await user.press(screen.getByTestId("decrement-Kiwi::Kyllingfilet"));
    expect(screen.getByTestId("qty-Kiwi::Kyllingfilet").props.children).toBe(1);

    await user.press(screen.getByTestId("decrement-Kiwi::Kyllingfilet"));
    expect(screen.getByTestId("item-count").props.children).toBe(0);
  });

  it("removeItem removes the line regardless of quantity", async () => {
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("increment-Kiwi::Kyllingfilet"));
    await user.press(screen.getByTestId("increment-Kiwi::Kyllingfilet"));

    await user.press(screen.getByTestId("remove-Kiwi::Kyllingfilet"));

    expect(screen.getByTestId("item-count").props.children).toBe(0);
  });

  it("toggleMealIdeaSelection flips selection for an eligible item", async () => {
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("add-eligible"));

    await user.press(screen.getByTestId("toggle-Kiwi::Kyllingfilet"));

    expect(screen.getByTestId("selected-Kiwi::Kyllingfilet").props.children).toBe("false");
  });

  it("toggleMealIdeaSelection has no effect on an ineligible item", async () => {
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("add-ineligible"));

    await user.press(screen.getByTestId("toggle-Kiwi::Coca-Cola"));

    expect(screen.getByTestId("selected-Kiwi::Coca-Cola").props.children).toBe("false");
  });

  it("groups items into foodItems and nonFoodItems by shopping_group", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("add-non-food"));

    expect(screen.getByTestId("food-count").props.children).toBe(1);
    expect(screen.getByTestId("non-food-count").props.children).toBe(1);
  });

  it("mealIdeaSelectedCount counts only eligible and selected items", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("add-ineligible"));
    await user.press(screen.getByTestId("add-non-food"));

    expect(screen.getByTestId("selected-count").props.children).toBe(1);
  });

  it("clearCart empties everything", async () => {
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("add-eligible"));
    await user.press(screen.getByTestId("add-non-food"));

    await user.press(screen.getByTestId("clear"));

    expect(screen.getByTestId("item-count").props.children).toBe(0);
  });

  it("persists the cart to AsyncStorage", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("add-eligible"));

    await waitFor(async () => {
      const stored = await AsyncStorage.getItem("cart");
      expect(stored).not.toBeNull();
      const parsed = JSON.parse(stored as string);
      expect(parsed).toHaveLength(1);
      expect(parsed[0].product_name).toBe("Kyllingfilet");
    });
  });

  it("loads a previously persisted cart on mount", async () => {
    await AsyncStorage.setItem(
      "cart",
      JSON.stringify([
        {
          cart_item_id: "Kiwi::Kyllingfilet",
          discount_item_id: "Kiwi::Kyllingfilet",
          product_name: "Kyllingfilet",
          normalized_product_name: "kyllingfilet",
          store_name: "Kiwi",
          current_price: 80,
          reference_price: null,
          image_url: null,
          shopping_group: "food",
          food_usage_class: "primary_ingredient",
          meal_role: "protein",
          recipe_eligible: true,
          quantity: 3,
          added_at: "2026-07-01T00:00:00.000Z",
          selected_for_meal_ideas: true,
        },
      ])
    );

    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("item-count").props.children).toBe(1));
    expect(screen.getByTestId("eligible-quantity").props.children).toBe(3);
  });

  it("ignores a corrupt persisted cart and starts empty", async () => {
    await AsyncStorage.setItem("cart", "not valid json{");

    await renderProbe();

    expect(screen.getByTestId("item-count").props.children).toBe(0);
  });
});

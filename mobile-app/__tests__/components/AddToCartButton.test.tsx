import AsyncStorage from "@react-native-async-storage/async-storage";
import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { AddToCartButton } from "../../src/components/AddToCartButton";
import type { DiscountedProduct } from "../../src/types/api";
import { renderWithProviders } from "../../test-utils/testUtils";

const DEAL: DiscountedProduct = {
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

describe("AddToCartButton", () => {
  afterEach(async () => {
    // Each test starts from a fresh, empty cart -- the cart is persisted to
    // AsyncStorage, which otherwise leaks state across tests in this file.
    await AsyncStorage.clear();
  });

  it("renders 'Add to cart' when the item is not yet in the cart", async () => {
    await renderWithProviders(<AddToCartButton deal={DEAL} />);

    expect(screen.getByTestId("add-to-cart-button")).toBeTruthy();
    expect(screen.getByText("Add to cart")).toBeTruthy();
    expect(screen.queryByTestId("cart-quantity-stepper")).toBeNull();
  });

  it("tapping Add to cart adds the item and switches to a quantity stepper showing 1", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<AddToCartButton deal={DEAL} />);

    await user.press(screen.getByTestId("add-to-cart-button"));

    expect(screen.queryByTestId("add-to-cart-button")).toBeNull();
    expect(screen.getByTestId("cart-quantity-stepper")).toBeTruthy();
    expect(screen.getByTestId("cart-quantity").props.children).toBe(1);
  });

  it("tapping + increases the quantity", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<AddToCartButton deal={DEAL} />);
    await user.press(screen.getByTestId("add-to-cart-button"));

    await user.press(screen.getByTestId("increment-quantity-button"));

    expect(screen.getByTestId("cart-quantity").props.children).toBe(2);
  });

  it("tapping - decreases the quantity and reverts to the Add to cart button at zero", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<AddToCartButton deal={DEAL} />);
    await user.press(screen.getByTestId("add-to-cart-button"));
    await user.press(screen.getByTestId("increment-quantity-button"));

    await user.press(screen.getByTestId("decrement-quantity-button"));
    expect(screen.getByTestId("cart-quantity").props.children).toBe(1);

    await user.press(screen.getByTestId("decrement-quantity-button"));
    expect(screen.queryByTestId("cart-quantity-stepper")).toBeNull();
    expect(screen.getByTestId("add-to-cart-button")).toBeTruthy();
  });
});

import AsyncStorage from "@react-native-async-storage/async-storage";
import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { MealIdeasScreen } from "../../src/screens/MealIdeasScreen";
import type { CartItem } from "../../src/types/cart";
import { renderWithProviders } from "../../test-utils/testUtils";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

function cartItem(overrides: Partial<CartItem>): CartItem {
  return {
    cart_item_id: "Kiwi::Kyllingfilet",
    discount_item_id: "Kiwi::Kyllingfilet",
    product_name: "Kyllingfilet",
    normalized_product_name: "kyllingfilet",
    store_name: "Kiwi",
    current_price: 80,
    reference_price: 100,
    image_url: null,
    shopping_group: "food",
    food_usage_class: "primary_ingredient",
    meal_role: "protein",
    recipe_eligible: true,
    quantity: 1,
    added_at: "2026-07-01T00:00:00.000Z",
    selected_for_meal_ideas: true,
    ...overrides,
  };
}

describe("MealIdeasScreen", () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    mockNavigate.mockReset();
  });

  it("shows both entry points", async () => {
    await renderWithProviders(<MealIdeasScreen />);

    expect(await screen.findByTestId("meal-ideas-from-cart-entry")).toBeTruthy();
    expect(screen.getByTestId("meal-ideas-from-store-entry")).toBeTruthy();
  });

  it("shows how many cart ingredients are selected", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([cartItem({}), cartItem({ cart_item_id: "Kiwi::Laks", discount_item_id: "Kiwi::Laks" })]));

    await renderWithProviders(<MealIdeasScreen />);

    expect(await screen.findByText("2 ingredients ready to use")).toBeTruthy();
  });

  it("navigates to the cart results screen when 'From my cart' is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<MealIdeasScreen />);

    await user.press(screen.getByTestId("meal-ideas-from-cart-entry"));

    expect(mockNavigate).toHaveBeenCalledWith("MealIdeasResults", { source: "cart" });
  });

  it("navigates to store selection when 'From a store's offers' is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<MealIdeasScreen />);

    await user.press(screen.getByTestId("meal-ideas-from-store-entry"));

    expect(mockNavigate).toHaveBeenCalledWith("MealIdeasStoreSelection");
  });
});

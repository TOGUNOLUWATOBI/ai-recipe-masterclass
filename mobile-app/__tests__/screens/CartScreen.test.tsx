import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { getDiscountedRecipes } from "../../src/api/client";
import { CartScreen } from "../../src/screens/CartScreen";
import type { CartItem } from "../../src/types/cart";
import { renderWithProviders } from "../../test-utils/testUtils";

jest.mock("../../src/api/client");
const mockedGetDiscountedRecipes = getDiscountedRecipes as jest.MockedFunction<typeof getDiscountedRecipes>;

// CartScreen renders with no real NavigationContainer/navigator in these tests (see
// renderWithProviders) -- the real useFocusEffect calls useNavigation() internally and
// throws outside one. Stand in with a mount effect, and expose the registered callback
// via mockRunFocusEffect so a test can simulate the Cart tab regaining focus.
const mockRunFocusEffect = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  const ReactActual = require("react");
  return {
    ...actual,
    useFocusEffect: (effect: () => void | (() => void)) => {
      mockRunFocusEffect.mockImplementation(effect);
      ReactActual.useEffect(effect, [effect]);
    },
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

async function seedCart(items: CartItem[]) {
  await AsyncStorage.setItem("cart", JSON.stringify(items));
}

function discountedResponseFor(items: CartItem[]) {
  return {
    discounted_ingredients: items.map((item) => ({
      product_name: item.product_name,
      category: "main_food" as const,
      current_price: item.current_price,
      reference_price: item.reference_price,
      discount_pct: null,
      unit_price: null,
      unit_price_unit: null,
      image_url: item.image_url,
      store_name: item.store_name,
      store_logo_url: null,
    })),
    source: null,
    count: 0,
    recipes: [],
    generated: null,
    error: null,
    updated_at: "2026-07-16T05:00:00Z",
  };
}

describe("CartScreen", () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    mockedGetDiscountedRecipes.mockReset();
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor([]));
    mockRunFocusEffect.mockReset();
  });

  it("shows an empty state when the cart has no items", async () => {
    await renderWithProviders(<CartScreen />);

    expect(await screen.findByTestId("cart-empty-state")).toBeTruthy();
  });

  it("renders a row for each cart item", async () => {
    const items = [cartItem({}), cartItem({ cart_item_id: "Kiwi::Laksefilet", product_name: "Laksefilet" })];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    expect(await screen.findByText("Kyllingfilet")).toBeTruthy();
    expect(screen.getByText("Laksefilet")).toBeTruthy();
    expect(screen.getAllByTestId("cart-item-row")).toHaveLength(2);
  });

  it("shows Food and Non-food section headers when the cart mixes both", async () => {
    const items = [
      cartItem({}),
      cartItem({
        cart_item_id: "Kiwi::Toalettpapir",
        product_name: "Toalettpapir",
        shopping_group: "non_food",
        food_usage_class: "not_applicable",
        recipe_eligible: false,
      }),
    ];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    expect(await screen.findByText("Food")).toBeTruthy();
    expect(screen.getByText("Non-food")).toBeTruthy();
  });

  it("does not show section headers when every item shares the same shopping_group", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    await screen.findByText("Kyllingfilet");
    expect(screen.queryByText("Food")).toBeNull();
    expect(screen.queryByText("Non-food")).toBeNull();
  });

  it("shows the meal-idea selection summary and toggling updates the count", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);
    const user = userEvent.setup();

    await renderWithProviders(<CartScreen />);

    expect(await screen.findByText("1 ingredient selected for meal ideas")).toBeTruthy();

    await user.press(screen.getByTestId("meal-idea-toggle"));

    expect(await screen.findByText("0 ingredients selected for meal ideas")).toBeTruthy();
  });

  it("does not show a meal-idea toggle for an ineligible item", async () => {
    const items = [
      cartItem({
        cart_item_id: "Kiwi::Cola",
        product_name: "Cola",
        food_usage_class: "beverage",
        recipe_eligible: false,
        selected_for_meal_ideas: false,
      }),
    ];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    await screen.findByText("Cola");
    expect(screen.queryByTestId("meal-idea-toggle")).toBeNull();
    expect(screen.getByText("Not used for meal suggestions")).toBeTruthy();
  });

  it("does not show a meal-idea toggle for a ready-meal item either -- Epic B4's disabled selection isn't beverage-specific", async () => {
    const items = [
      cartItem({
        cart_item_id: "Kiwi::Ferdigpizza",
        product_name: "Ferdigpizza",
        food_usage_class: "ready_meal",
        recipe_eligible: false,
        selected_for_meal_ideas: false,
      }),
    ];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    await screen.findByText("Ferdigpizza");
    expect(screen.queryByTestId("meal-idea-toggle")).toBeNull();
    expect(screen.getByText("Not used for meal suggestions")).toBeTruthy();
  });

  it("+ and - adjust an item's quantity", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);
    const user = userEvent.setup();

    await renderWithProviders(<CartScreen />);
    await screen.findByText("Kyllingfilet");

    await user.press(screen.getByTestId("cart-increment-button"));
    expect(screen.getByTestId("cart-item-quantity").props.children).toBe(2);

    await user.press(screen.getByTestId("cart-decrement-button"));
    expect(screen.getByTestId("cart-item-quantity").props.children).toBe(1);
  });

  it("the remove button removes the item from the cart", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);
    const user = userEvent.setup();

    await renderWithProviders(<CartScreen />);
    await screen.findByText("Kyllingfilet");

    await user.press(screen.getByTestId("cart-remove-button"));

    expect(await screen.findByTestId("cart-empty-state")).toBeTruthy();
  });

  it("flags an item as possibly expired when it's no longer in the latest discount snapshot (Epic B6)", async () => {
    const items = [cartItem({})];
    // The latest snapshot no longer contains this product at all.
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor([]));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    expect(await screen.findByTestId("expired-badge")).toBeTruthy();
    // The stale discount must not keep being shown as though it were still current.
    expect(screen.queryByText("100,00 kr")).toBeNull();
  });

  it("does not flag an item as expired when it's still in the latest snapshot", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    await screen.findByText("Kyllingfilet");
    expect(screen.queryByTestId("expired-badge")).toBeNull();
  });

  it("re-fetches the discount snapshot when the Cart tab regains focus", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);
    await screen.findByText("Kyllingfilet");

    expect(mockedGetDiscountedRecipes).toHaveBeenCalledTimes(1);

    // Simulates the Cart tab regaining focus after the user browsed elsewhere -- the
    // snapshot may have changed in the background (cron-refreshed), so this must not
    // just be a mount-only fetch.
    await act(async () => {
      mockRunFocusEffect();
    });

    expect(mockedGetDiscountedRecipes).toHaveBeenCalledTimes(2);
  });

  it("a failed snapshot fetch does not flag anything as expired or break the screen", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockRejectedValue(new Error("network down"));
    await seedCart(items);

    await renderWithProviders(<CartScreen />);

    await screen.findByText("Kyllingfilet");
    expect(screen.queryByTestId("expired-badge")).toBeNull();
  });

  it("Clear cart asks for confirmation and only clears on confirm", async () => {
    const items = [cartItem({})];
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor(items));
    await seedCart(items);
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const user = userEvent.setup();

    await renderWithProviders(<CartScreen />);
    await screen.findByText("Kyllingfilet");

    await user.press(screen.getByTestId("clear-cart-button"));

    expect(alertSpy).toHaveBeenCalledTimes(1);
    const buttons = alertSpy.mock.calls[0][2] as { text: string; onPress?: () => void }[];
    const confirmButton = buttons.find((b) => b.text === "Clear cart");

    // Must be the async form: confirmButton.onPress() is invoked outside of any real
    // user gesture (there's no native Alert in this test environment to press), and
    // only await act(async () => ...) reliably flushes the resulting setState here --
    // a synchronous act() left the cart showing its pre-clear contents.
    await act(async () => {
      confirmButton?.onPress?.();
    });

    expect(await screen.findByTestId("cart-empty-state")).toBeTruthy();
    alertSpy.mockRestore();
  });
});

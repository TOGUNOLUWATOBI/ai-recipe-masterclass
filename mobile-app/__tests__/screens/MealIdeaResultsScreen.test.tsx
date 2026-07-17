import AsyncStorage from "@react-native-async-storage/async-storage";
import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { Text, TouchableOpacity } from "react-native";
import { getIngredientOffers, getMealIdeasFromCart, getMealIdeasFromStore } from "../../src/api/client";
import { useCart } from "../../src/cart/CartContext";
import { MealIdeaResultsScreen } from "../../src/screens/MealIdeaResultsScreen";
import type { IngredientOffer, MealIdea } from "../../src/types/api";
import type { CartItem } from "../../src/types/cart";
import { renderWithProviders } from "../../test-utils/testUtils";

jest.mock("../../src/api/client");
const mockedGetMealIdeasFromCart = getMealIdeasFromCart as jest.MockedFunction<typeof getMealIdeasFromCart>;
const mockedGetMealIdeasFromStore = getMealIdeasFromStore as jest.MockedFunction<typeof getMealIdeasFromStore>;
const mockedGetIngredientOffers = getIngredientOffers as jest.MockedFunction<typeof getIngredientOffers>;

let mockRouteParams: { source: "cart" } | { source: "store"; storeName: string } = { source: "cart" };
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useRoute: () => ({ params: mockRouteParams }),
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

function idea(overrides: Partial<MealIdea>): MealIdea {
  return {
    title: "Chicken and Rice",
    description: null,
    servings: null,
    completion_status: "complete",
    selected_items_used: ["chicken fillet"],
    required_ingredients: [{ name: "chicken fillet", quantity: null }],
    optional_ingredients: [],
    missing_required_ingredients: [],
    ingredient_coverage_percentage: 100,
    pantry_basics_assumed: [],
    estimated_complexity: null,
    source_type: "retrieved",
    ...overrides,
  };
}

function offer(overrides: Partial<IngredientOffer>): IngredientOffer {
  return {
    normalized_ingredient_key: "chicken fillet",
    ingredient_aliases: ["chicken fillet", "chicken fillets"],
    original_product_name: "KYLLINGFILET",
    store_name: "Kiwi",
    current_price: 80,
    reference_price: 100,
    discount_pct: 20,
    unit_price: 160,
    unit_price_unit: "kg",
    image_url: null,
    store_logo_url: null,
    valid_from: null,
    valid_until: null,
    shopping_group: "food",
    food_usage_class: "primary_ingredient",
    meal_role: "protein",
    recipe_eligible: true,
    snapshot_id: null,
    updated_at: null,
    match_confidence: "exact",
    ...overrides,
  };
}

describe("MealIdeaResultsScreen", () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    mockedGetMealIdeasFromCart.mockReset();
    mockedGetMealIdeasFromStore.mockReset();
    mockedGetIngredientOffers.mockReset();
    mockedGetIngredientOffers.mockResolvedValue({ snapshot_updated_at: null, ingredients: [] });
    mockRouteParams = { source: "cart" };
  });

  it("cart source: shows the select-an-ingredient empty state without calling the API when nothing is selected", async () => {
    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByText("Select at least one eligible ingredient in your cart to get meal ideas.")).toBeTruthy();
    expect(mockedGetMealIdeasFromCart).not.toHaveBeenCalled();
  });

  it("cart source: requests ideas for eligible, selected cart items only", async () => {
    await AsyncStorage.setItem(
      "cart",
      JSON.stringify([
        cartItem({}),
        cartItem({
          cart_item_id: "Kiwi::Cola", discount_item_id: "Kiwi::Cola", product_name: "Cola",
          recipe_eligible: false, selected_for_meal_ideas: false,
        }),
        cartItem({
          cart_item_id: "Kiwi::Laks", discount_item_id: "Kiwi::Laks", product_name: "Laksefilet",
          recipe_eligible: true, selected_for_meal_ideas: false,
        }),
      ])
    );
    mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByText("Chicken and Rice")).toBeTruthy();
    expect(mockedGetMealIdeasFromCart).toHaveBeenCalledWith(["Kiwi::Kyllingfilet"], 5, "en");
  });

  it("cart source: a fetched-but-empty result shows the generic no-ideas message, not the select-an-ingredient prompt", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
    mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [], excluded_cart_items: [], source: null });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByText("No meal ideas found for these ingredients right now.")).toBeTruthy();
  });

  it("cart source: missing ingredients use 'Still need' wording", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
    mockedGetMealIdeasFromCart.mockResolvedValue({
      ideas: [idea({ missing_required_ingredients: ["rice"] })],
      excluded_cart_items: [],
      source: "retrieved",
    });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByTestId("meal-idea-missing")).toHaveTextContent("Still need: rice");
  });

  it("store source: requests ideas for the picked store and shows the store heading", async () => {
    mockRouteParams = { source: "store", storeName: "Kiwi" };
    mockedGetMealIdeasFromStore.mockResolvedValue({
      ideas: [idea({})], excluded_store_items: [], store_name: "Kiwi", source: "retrieved",
    });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByText("From Kiwi's offers")).toBeTruthy();
    expect(mockedGetMealIdeasFromStore).toHaveBeenCalledWith("Kiwi", 5, "en");
  });

  it("store source: missing ingredients use 'Not found in the current offers' wording, never 'unavailable' (Task E5)", async () => {
    mockRouteParams = { source: "store", storeName: "Kiwi" };
    mockedGetMealIdeasFromStore.mockResolvedValue({
      ideas: [idea({ missing_required_ingredients: ["lemon"] })],
      excluded_store_items: [],
      store_name: "Kiwi",
      source: "retrieved",
    });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByTestId("meal-idea-missing")).toHaveTextContent("Not found in the current offers: lemon");
    expect(screen.queryByText(/unavailable/i)).toBeNull();
  });

  it("store source: an empty result shows the store-specific empty state", async () => {
    mockRouteParams = { source: "store", storeName: "Kiwi" };
    mockedGetMealIdeasFromStore.mockResolvedValue({ ideas: [], excluded_store_items: [], store_name: "Kiwi", source: null });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByText("No meal ideas available from Kiwi's current offers right now.")).toBeTruthy();
  });

  it("shows optional ingredients and the pantry-basics note", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
    mockedGetMealIdeasFromCart.mockResolvedValue({
      ideas: [
        idea({
          optional_ingredients: [{ name: "black pepper", quantity: null }],
          pantry_basics_assumed: ["salt", "water", "cooking oil"],
        }),
      ],
      excluded_cart_items: [],
      source: "retrieved",
    });

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByTestId("meal-idea-optional")).toHaveTextContent("Optional: black pepper");
    expect(screen.getByText("You may already have this at home: salt, water, cooking oil")).toBeTruthy();
  });

  it("shows an error banner when the fetch fails", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
    mockedGetMealIdeasFromCart.mockRejectedValue(new Error("network down"));

    await renderWithProviders(<MealIdeaResultsScreen />);

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
  });

  it("does not re-fetch when an unrelated cart mutation changes the cart array's identity but not the eligible/selected set", async () => {
    function IncrementUnrelatedItem() {
      const { incrementQuantity } = useCart();
      return (
        <TouchableOpacity testID="mutate-unrelated-item" onPress={() => incrementQuantity("Kiwi::Laks")}>
          <Text>mutate</Text>
        </TouchableOpacity>
      );
    }

    await AsyncStorage.setItem(
      "cart",
      JSON.stringify([
        cartItem({}),
        cartItem({
          cart_item_id: "Kiwi::Laks", discount_item_id: "Kiwi::Laks", product_name: "Laksefilet",
          recipe_eligible: true, selected_for_meal_ideas: false,
        }),
      ])
    );
    mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
    const user = userEvent.setup();

    await renderWithProviders(
      <>
        <MealIdeaResultsScreen />
        <IncrementUnrelatedItem />
      </>
    );
    await screen.findByText("Chicken and Rice");
    expect(mockedGetMealIdeasFromCart).toHaveBeenCalledTimes(1);

    // Bumps quantity on an item that isn't selected for meal ideas -- the cart array
    // gets a new reference, but the eligible+selected id set is unchanged.
    await user.press(screen.getByTestId("mutate-unrelated-item"));

    expect(mockedGetMealIdeasFromCart).toHaveBeenCalledTimes(1);
  });

  it("does re-fetch when a cart mutation actually changes the eligible/selected set", async () => {
    function ToggleSelection() {
      const { toggleMealIdeaSelection } = useCart();
      return (
        <TouchableOpacity testID="toggle-selection" onPress={() => toggleMealIdeaSelection("Kiwi::Laks")}>
          <Text>toggle</Text>
        </TouchableOpacity>
      );
    }

    await AsyncStorage.setItem(
      "cart",
      JSON.stringify([
        cartItem({}),
        cartItem({
          cart_item_id: "Kiwi::Laks", discount_item_id: "Kiwi::Laks", product_name: "Laksefilet",
          recipe_eligible: true, selected_for_meal_ideas: false,
        }),
      ])
    );
    mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
    const user = userEvent.setup();

    await renderWithProviders(
      <>
        <MealIdeaResultsScreen />
        <ToggleSelection />
      </>
    );
    await screen.findByText("Chicken and Rice");
    expect(mockedGetMealIdeasFromCart).toHaveBeenCalledTimes(1);
    expect(mockedGetMealIdeasFromCart).toHaveBeenLastCalledWith(["Kiwi::Kyllingfilet"], 5, "en");

    // Selects the salmon too -- now part of the eligible+selected set.
    await user.press(screen.getByTestId("toggle-selection"));

    expect(mockedGetMealIdeasFromCart).toHaveBeenCalledTimes(2);
    expect(mockedGetMealIdeasFromCart).toHaveBeenLastCalledWith(["Kiwi::Kyllingfilet", "Kiwi::Laks"], 5, "en");
  });

  describe("Epic F5-F7: 'On offer this week' section", () => {
    it("fetches offers once for the union of required/optional ingredients across all ideas", async () => {
      await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
      mockedGetMealIdeasFromCart.mockResolvedValue({
        ideas: [
          idea({
            title: "Chicken and Rice",
            required_ingredients: [{ name: "chicken fillet", quantity: null }, { name: "rice", quantity: null }],
            optional_ingredients: [{ name: "lemon", quantity: null }],
          }),
          idea({
            title: "Chicken Soup",
            required_ingredients: [{ name: "chicken fillet", quantity: null }], // duplicate across ideas
            optional_ingredients: [],
          }),
        ],
        excluded_cart_items: [],
        source: "retrieved",
      });

      await renderWithProviders(<MealIdeaResultsScreen />);
      await screen.findByText("Chicken and Rice");

      expect(mockedGetIngredientOffers).toHaveBeenCalledTimes(1);
      expect(mockedGetIngredientOffers).toHaveBeenCalledWith(["chicken fillet", "rice", "lemon"], 3);
    });

    it("shows the matched offer's product name, store, and price", async () => {
      await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
      mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
      mockedGetIngredientOffers.mockResolvedValue({
        snapshot_updated_at: "2026-07-16T05:00:00Z",
        ingredients: [{ ingredient: "chicken fillet", offers: [offer({})] }],
      });

      await renderWithProviders(<MealIdeaResultsScreen />);

      expect(await screen.findByTestId("on-offer-section")).toBeTruthy();
      expect(await screen.findByTestId("ingredient-offer-row")).toHaveTextContent(/KYLLINGFILET · Kiwi/);
      expect(screen.getByText("80,00 kr")).toBeTruthy();
    });

    it("shows 'No current offer found' when nothing matches -- never 'unavailable'", async () => {
      await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
      mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
      mockedGetIngredientOffers.mockResolvedValue({
        snapshot_updated_at: "2026-07-16T05:00:00Z",
        ingredients: [{ ingredient: "chicken fillet", offers: [] }],
      });

      await renderWithProviders(<MealIdeaResultsScreen />);

      expect(await screen.findByTestId("no-offer-found")).toHaveTextContent("No current offer found");
      expect(screen.queryByText(/unavailable/i)).toBeNull();
    });

    it("labels a fuzzy match as a possible match rather than presenting it as confirmed", async () => {
      await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
      mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
      mockedGetIngredientOffers.mockResolvedValue({
        snapshot_updated_at: "2026-07-16T05:00:00Z",
        ingredients: [{ ingredient: "chicken fillet", offers: [offer({ match_confidence: "fuzzy" })] }],
      });

      await renderWithProviders(<MealIdeaResultsScreen />);

      expect(await screen.findByTestId("ingredient-offer-row")).toHaveTextContent(/Possible match/);
    });

    it("shows only the top offer initially, expanding to the rest via 'view more'", async () => {
      await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
      mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
      mockedGetIngredientOffers.mockResolvedValue({
        snapshot_updated_at: "2026-07-16T05:00:00Z",
        ingredients: [{
          ingredient: "chicken fillet",
          offers: [
            offer({ store_name: "Kiwi", unit_price: 150 }),
            offer({ store_name: "Meny", unit_price: 180 }),
            offer({ store_name: "Extra", unit_price: 190 }),
          ],
        }],
      });
      const user = userEvent.setup();

      await renderWithProviders(<MealIdeaResultsScreen />);
      await screen.findByTestId("on-offer-section");

      expect(screen.getAllByTestId("ingredient-offer-row")).toHaveLength(1);
      expect(await screen.findByTestId("view-more-offers")).toHaveTextContent("View 2 more offers");

      await user.press(screen.getByTestId("view-more-offers"));

      expect(screen.getAllByTestId("ingredient-offer-row")).toHaveLength(3);
      expect(screen.getByText("Show fewer offers")).toBeTruthy();
    });

    it("a failed offers lookup does not break the meal ideas themselves", async () => {
      await AsyncStorage.setItem("cart", JSON.stringify([cartItem({})]));
      mockedGetMealIdeasFromCart.mockResolvedValue({ ideas: [idea({})], excluded_cart_items: [], source: "retrieved" });
      mockedGetIngredientOffers.mockRejectedValue(new Error("network down"));

      await renderWithProviders(<MealIdeaResultsScreen />);

      expect(await screen.findByText("Chicken and Rice")).toBeTruthy();
      expect(await screen.findByTestId("no-offer-found")).toBeTruthy();
    });
  });
});

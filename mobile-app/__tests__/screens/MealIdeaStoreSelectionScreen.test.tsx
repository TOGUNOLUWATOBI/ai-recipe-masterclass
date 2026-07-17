import { screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { getDiscountedRecipes } from "../../src/api/client";
import { MealIdeaStoreSelectionScreen } from "../../src/screens/MealIdeaStoreSelectionScreen";
import type { DiscountedProduct } from "../../src/types/api";
import { renderWithProviders } from "../../test-utils/testUtils";

jest.mock("../../src/api/client");
const mockedGetDiscountedRecipes = getDiscountedRecipes as jest.MockedFunction<typeof getDiscountedRecipes>;

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

function deal(overrides: Partial<DiscountedProduct>): DiscountedProduct {
  return {
    product_name: "Kyllingfilet",
    category: "main_food",
    current_price: 80,
    reference_price: 100,
    discount_pct: 20,
    unit_price: null,
    unit_price_unit: null,
    image_url: null,
    store_name: "Kiwi",
    store_logo_url: null,
    ...overrides,
  };
}

function discountedResponseFor(deals: DiscountedProduct[]) {
  return {
    discounted_ingredients: deals,
    source: null,
    count: 0,
    recipes: [],
    generated: null,
    error: null,
    updated_at: "2026-07-16T05:00:00Z",
  };
}

describe("MealIdeaStoreSelectionScreen", () => {
  beforeEach(() => {
    mockedGetDiscountedRecipes.mockReset();
    mockNavigate.mockReset();
  });

  it("lists distinct store names from the cached snapshot", async () => {
    mockedGetDiscountedRecipes.mockResolvedValue(
      discountedResponseFor([deal({ store_name: "Kiwi" }), deal({ store_name: "Meny" }), deal({ store_name: "Kiwi" })])
    );

    await renderWithProviders(<MealIdeaStoreSelectionScreen />);

    expect(await screen.findByText("Kiwi")).toBeTruthy();
    expect(screen.getByText("Meny")).toBeTruthy();
    expect(screen.getAllByTestId("store-selection-row")).toHaveLength(2);
  });

  it("never requests recipe generation -- a fast cache read only (Task E2's hard rule)", async () => {
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor([deal({})]));

    await renderWithProviders(<MealIdeaStoreSelectionScreen />);
    await waitFor(() => expect(mockedGetDiscountedRecipes).toHaveBeenCalled());

    expect(mockedGetDiscountedRecipes.mock.calls[0][1]).toBe(false);
  });

  it("shows an empty state when no stores have current offers", async () => {
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor([]));

    await renderWithProviders(<MealIdeaStoreSelectionScreen />);

    expect(await screen.findByText("No stores with current offers found.")).toBeTruthy();
  });

  it("navigates to the results screen with the picked store on press", async () => {
    mockedGetDiscountedRecipes.mockResolvedValue(discountedResponseFor([deal({ store_name: "Kiwi" })]));
    const user = userEvent.setup();

    await renderWithProviders(<MealIdeaStoreSelectionScreen />);
    await screen.findByText("Kiwi");

    await user.press(screen.getByText("Kiwi"));

    expect(mockNavigate).toHaveBeenCalledWith("MealIdeasResults", { source: "store", storeName: "Kiwi" });
  });

  it("shows an error banner when the fetch fails", async () => {
    mockedGetDiscountedRecipes.mockRejectedValue(new Error("network down"));

    await renderWithProviders(<MealIdeaStoreSelectionScreen />);

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
  });
});

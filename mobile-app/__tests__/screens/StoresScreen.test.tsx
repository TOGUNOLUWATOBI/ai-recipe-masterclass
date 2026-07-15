import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { getDiscountedRecipes } from "../../src/api/client";
import { ApiError } from "../../src/api/errors";
import { StoresScreen } from "../../src/screens/StoresScreen";
import type { DiscountedProduct } from "../../src/types/api";
import { renderWithProviders } from "../../test-utils/testUtils";

jest.mock("../../src/api/client");

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

const mockedGetDiscounted = getDiscountedRecipes as jest.MockedFunction<typeof getDiscountedRecipes>;

function makeDeal(overrides: Partial<DiscountedProduct> = {}): DiscountedProduct {
  return {
    product_name: "Camembert Le Rustique 250g",
    category: "main_food",
    current_price: 68.9,
    reference_price: 129,
    discount_pct: 46.6,
    unit_price: null,
    unit_price_unit: null,
    image_url: "https://example.com/cheese.jpg",
    store_name: "Coop",
    store_logo_url: "https://example.com/coop-logo.svg",
    ...overrides,
  };
}

describe("StoresScreen", () => {
  beforeEach(() => {
    mockedGetDiscounted.mockReset();
    mockNavigate.mockReset();
  });

  it("fetches deals automatically on mount, fast-path (no recipe generation)", async () => {
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [makeDeal()],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: "2026-07-08T09:19:17.306962+00:00",
    });

    await renderWithProviders(<StoresScreen />);

    expect(mockedGetDiscounted).toHaveBeenCalledWith(20, false);
    expect(await screen.findByText("Coop")).toBeTruthy();
  });

  it("shows one tile per store with the item count, not the raw item list", async () => {
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [
        makeDeal({ store_name: "Coop", product_name: "Product A" }),
        makeDeal({ store_name: "Coop", product_name: "Product B", discount_pct: null, reference_price: null }),
        makeDeal({ store_name: "Kiwi", product_name: "Product C" }),
      ],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: null,
    });

    await renderWithProviders(<StoresScreen />);

    expect(await screen.findByText("Coop")).toBeTruthy();
    expect(screen.getByText("Kiwi")).toBeTruthy();
    // Coop: 2 total items, only 1 of them actually discounted
    expect(screen.getByText("2 items · 1 on sale")).toBeTruthy();
    // Kiwi: 1 item, discounted -- still called out
    expect(screen.getByText("1 items · 1 on sale")).toBeTruthy();
    expect(screen.queryByText("Product A")).toBeNull();
    expect(screen.queryByText("Product C")).toBeNull();
  });

  it("shows a friendly empty state when nothing is found", async () => {
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: null,
    });

    await renderWithProviders(<StoresScreen />);

    expect(await screen.findByText(/No items found/)).toBeTruthy();
  });

  it("shows a backend-reported error message", async () => {
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: "discount cache not available",
      updated_at: null,
    });

    await renderWithProviders(<StoresScreen />);

    expect(await screen.findByText("discount cache not available")).toBeTruthy();
  });

  it("shows an error banner when the request fails outright", async () => {
    mockedGetDiscounted.mockRejectedValueOnce(new ApiError("network", "no connection"));

    await renderWithProviders(<StoresScreen />);

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
  });

  it("defaults to the Food tab, showing main_food and snack but not non_food items", async () => {
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [
        makeDeal({
          store_name: "Coop", product_name: "Kyllingfilet", category: "main_food",
          discount_pct: null, reference_price: null,
        }),
        makeDeal({
          store_name: "Coop", product_name: "Melkesjokolade", category: "snack",
          discount_pct: null, reference_price: null,
        }),
        makeDeal({
          store_name: "Kiwi", product_name: "Toalettpapir", category: "non_food",
          discount_pct: null, reference_price: null,
        }),
      ],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: null,
    });

    await renderWithProviders(<StoresScreen />);

    // Coop groups its two food items (main_food + snack); Kiwi's only item is non_food
    // and shouldn't count toward the Food tab at all.
    expect(await screen.findByText("Coop")).toBeTruthy();
    expect(screen.queryByText("Kiwi")).toBeNull();
    expect(screen.getByText("2 items")).toBeTruthy();
  });

  it("switches to the Non-food tab and shows only non_food items", async () => {
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [
        makeDeal({ store_name: "Coop", product_name: "Kyllingfilet", category: "main_food" }),
        makeDeal({ store_name: "Kiwi", product_name: "Toalettpapir", category: "non_food" }),
      ],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: null,
    });

    const user = userEvent.setup();
    await renderWithProviders(<StoresScreen />);
    await screen.findByTestId("non-food-tab-button");
    await user.press(screen.getByTestId("non-food-tab-button"));

    expect(await screen.findByText("Kiwi")).toBeTruthy();
    expect(screen.queryByText("Coop")).toBeNull();
  });

  it("treats a missing category as a food item, not non-food", async () => {
    const { category: _category, ...dealWithoutCategory } = makeDeal({ store_name: "Coop" });
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [dealWithoutCategory as DiscountedProduct],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: null,
    });

    await renderWithProviders(<StoresScreen />);

    expect(await screen.findByText("Coop")).toBeTruthy();
  });

  it("navigates to StoreItems with the tapped store's full deal group", async () => {
    const deal = makeDeal();
    mockedGetDiscounted.mockResolvedValueOnce({
      discounted_ingredients: [deal],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: null,
      updated_at: null,
    });

    const user = userEvent.setup();
    await renderWithProviders(<StoresScreen />);
    await screen.findByTestId("store-card");
    await user.press(screen.getByTestId("store-card"));

    expect(mockNavigate).toHaveBeenCalledWith("StoreItems", {
      store: { storeName: "Coop", storeLogoUrl: deal.store_logo_url, deals: [deal] },
    });
  });
});

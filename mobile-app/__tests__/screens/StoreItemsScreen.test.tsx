import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { StoreItemsScreen } from "../../src/screens/StoreItemsScreen";
import type { DiscountedProduct } from "../../src/types/api";
import { renderWithProviders } from "../../test-utils/testUtils";

const DEALS: DiscountedProduct[] = [
  {
    product_name: "Camembert Le Rustique 250g", category: "main_food", current_price: 68.9,
    reference_price: 129, discount_pct: 46.6, unit_price: null, unit_price_unit: null, image_url: null,
    store_name: "Coop", store_logo_url: null,
  },
  {
    product_name: "Idun Rømmedressing 435g", category: "main_food", current_price: 39.9,
    reference_price: 52.05, discount_pct: 23.3, unit_price: null, unit_price_unit: null, image_url: null,
    store_name: "Coop", store_logo_url: null,
  },
];

const mockStore = { storeName: "Coop", storeLogoUrl: null, deals: DEALS };

const mockNavigate = jest.fn();
const mockUseRoute = jest.fn(() => ({ params: { store: mockStore } }));
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
    useRoute: () => mockUseRoute(),
  };
});

describe("StoreItemsScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockUseRoute.mockReturnValue({ params: { store: mockStore } });
  });

  it("renders a deal card for every item in the store's group", async () => {
    await renderWithProviders(<StoreItemsScreen />);

    expect(screen.getByText("Camembert Le Rustique 250g")).toBeTruthy();
    expect(screen.getByText("Idun Rømmedressing 435g")).toBeTruthy();
  });

  it("navigates to the deal detail screen with the tapped deal", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<StoreItemsScreen />);

    const cards = screen.getAllByTestId("deal-card");
    await user.press(cards[0]);

    expect(mockNavigate).toHaveBeenCalledWith("DealDetail", { deal: DEALS[0] });
  });

  it("does not show a section header when every item in the store is the same category", async () => {
    await renderWithProviders(<StoreItemsScreen />);

    expect(screen.queryByText("Food")).toBeNull();
    expect(screen.queryByText("Snacks")).toBeNull();
  });
});

describe("StoreItemsScreen with mixed categories", () => {
  const mixedStore = {
    storeName: "Coop",
    storeLogoUrl: null,
    deals: [
      { ...DEALS[0], product_name: "Kyllingfilet", category: "main_food" as const },
      { ...DEALS[0], product_name: "Freia Melkesjokolade", category: "snack" as const },
    ],
  };

  beforeEach(() => {
    mockNavigate.mockReset();
    mockUseRoute.mockReturnValue({ params: { store: mixedStore } });
  });

  it("splits a store's items into Food and Snacks sections", async () => {
    await renderWithProviders(<StoreItemsScreen />);

    expect(await screen.findByText("Food")).toBeTruthy();
    expect(screen.getByText("Snacks")).toBeTruthy();
    expect(screen.getByText("Kyllingfilet")).toBeTruthy();
    expect(screen.getByText("Freia Melkesjokolade")).toBeTruthy();
  });
});

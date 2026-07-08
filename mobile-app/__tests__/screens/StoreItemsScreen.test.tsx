import { render, screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { StoreItemsScreen } from "../../src/screens/StoreItemsScreen";
import type { DiscountedProduct } from "../../src/types/api";

const DEALS: DiscountedProduct[] = [
  {
    category: "Ost", product_name: "Camembert Le Rustique 250g", current_price: 68.9,
    reference_price: 129, discount_pct: 46.6, unit_price: null, image_url: null,
    store_name: "Coop", store_logo_url: null,
  },
  {
    category: "Rømme", product_name: "Idun Rømmedressing 435g", current_price: 39.9,
    reference_price: 52.05, discount_pct: 23.3, unit_price: null, image_url: null,
    store_name: "Coop", store_logo_url: null,
  },
];

const mockStore = { storeName: "Coop", storeLogoUrl: null, deals: DEALS };

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
    useRoute: () => ({ params: { store: mockStore } }),
  };
});

describe("StoreItemsScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  it("renders a deal card for every item in the store's group", async () => {
    await render(<StoreItemsScreen />);

    expect(screen.getByText("Camembert Le Rustique 250g")).toBeTruthy();
    expect(screen.getByText("Idun Rømmedressing 435g")).toBeTruthy();
  });

  it("navigates to the deal detail screen with the tapped deal", async () => {
    const user = userEvent.setup();
    await render(<StoreItemsScreen />);

    const cards = screen.getAllByTestId("deal-card");
    await user.press(cards[0]);

    expect(mockNavigate).toHaveBeenCalledWith("DealDetail", { deal: DEALS[0] });
  });
});

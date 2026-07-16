import AsyncStorage from "@react-native-async-storage/async-storage";
import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { DealCard } from "../../src/components/DealCard";
import type { DiscountedProduct } from "../../src/types/api";
import { renderWithProviders } from "../../test-utils/testUtils";

const DEAL: DiscountedProduct = {
  product_name: "Camembert Le Rustique 250g",
  category: "main_food",
  current_price: 68.9,
  reference_price: 129,
  discount_pct: 46.6,
  unit_price: 27.56,
  unit_price_unit: "kg",
  image_url: "https://example.com/cheese.jpg",
  store_name: "Coop",
  store_logo_url: "https://example.com/coop-logo.svg",
};

describe("DealCard", () => {
  afterEach(async () => {
    // The cart persists to AsyncStorage across tests in this file otherwise.
    await AsyncStorage.clear();
  });

  it("renders product name, prices, and a rounded discount badge", async () => {
    await renderWithProviders(<DealCard deal={DEAL} onPress={() => {}} />);

    expect(screen.getByText("Camembert Le Rustique 250g")).toBeTruthy();
    expect(screen.getByText("68,90 kr")).toBeTruthy();
    expect(screen.getByText("129,00 kr")).toBeTruthy();
    expect(screen.getByText("-47%")).toBeTruthy();
    expect(screen.getByText("27,56 kr/kg")).toBeTruthy();
  });

  it("falls back to the generic '/unit' label if unit_price_unit is unexpectedly null", async () => {
    await renderWithProviders(<DealCard deal={{ ...DEAL, unit_price_unit: null }} onPress={() => {}} />);

    expect(screen.getByText("27,56 kr/unit")).toBeTruthy();
  });

  it("shows a placeholder icon when there is no product image", async () => {
    await renderWithProviders(<DealCard deal={{ ...DEAL, image_url: null }} onPress={() => {}} />);

    expect(screen.getByText("🛒")).toBeTruthy();
  });

  it("renders a plain listing with no badge or strike-through price when there is no computable discount", async () => {
    const noDiscount: DiscountedProduct = { ...DEAL, discount_pct: null, reference_price: null };
    await renderWithProviders(<DealCard deal={noDiscount} onPress={() => {}} />);

    expect(screen.getByText("Camembert Le Rustique 250g")).toBeTruthy();
    expect(screen.getByText("68,90 kr")).toBeTruthy();
    expect(screen.queryByText("129,00 kr")).toBeNull();
    expect(screen.queryByText("-47%")).toBeNull();
  });

  it("calls onPress when the card itself is tapped", async () => {
    const onPress = jest.fn();
    const user = userEvent.setup();
    await renderWithProviders(<DealCard deal={DEAL} onPress={onPress} />);

    await user.press(screen.getByTestId("deal-card"));

    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("shows an Add to cart control", async () => {
    await renderWithProviders(<DealCard deal={DEAL} onPress={() => {}} />);

    expect(screen.getByTestId("add-to-cart-button")).toBeTruthy();
  });

  it("tapping Add to cart does not also trigger the card's onPress (Epic B1)", async () => {
    const onPress = jest.fn();
    const user = userEvent.setup();
    await renderWithProviders(<DealCard deal={DEAL} onPress={onPress} />);

    await user.press(screen.getByTestId("add-to-cart-button"));

    expect(onPress).not.toHaveBeenCalled();
    expect(screen.getByTestId("cart-quantity-stepper")).toBeTruthy();
    expect(screen.getByTestId("cart-quantity").props.children).toBe(1);
  });
});

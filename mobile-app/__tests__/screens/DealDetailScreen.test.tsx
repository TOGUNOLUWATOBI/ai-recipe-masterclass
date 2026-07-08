import { render, screen, waitFor } from "@testing-library/react-native";
import React from "react";
import { getRecipesFromIngredients } from "../../src/api/client";
import { ApiError } from "../../src/api/errors";
import { DealDetailScreen } from "../../src/screens/DealDetailScreen";
import type { DiscountedProduct } from "../../src/types/api";

jest.mock("../../src/api/client");

const DEAL: DiscountedProduct = {
  category: "Ost",
  product_name: "Camembert Le Rustique 250g",
  current_price: 68.9,
  reference_price: 129,
  discount_pct: 46.6,
  unit_price: null,
  image_url: "https://example.com/cheese.jpg",
  store_name: "Coop",
  store_logo_url: null,
};

const mockUseRoute = jest.fn(() => ({ params: { deal: DEAL } }));
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useRoute: () => mockUseRoute(),
  };
});

const mockedGetRecipes = getRecipesFromIngredients as jest.MockedFunction<typeof getRecipesFromIngredients>;

describe("DealDetailScreen", () => {
  beforeEach(() => {
    mockedGetRecipes.mockReset();
    mockUseRoute.mockReturnValue({ params: { deal: DEAL } });
  });

  it("requests a recipe for exactly the tapped product", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 1,
      recipes: [{ title: "Cheese Board", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    await render(<DealDetailScreen />);

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledWith([DEAL.product_name], 5));
    expect(await screen.findByText("Cheese Board")).toBeTruthy();
  });

  it("shows the deal's price, store, and discount info", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 0,
      recipes: [],
      generated: null,
      error: null,
    });

    await render(<DealDetailScreen />);

    expect(screen.getByText("Camembert Le Rustique 250g")).toBeTruthy();
    expect(screen.getByText("Coop")).toBeTruthy();
    expect(screen.getByText("68,90 kr")).toBeTruthy();
    expect(screen.getByText("-47%")).toBeTruthy();
  });

  it("renders a plain price with no badge or strike-through when there is no computable discount", async () => {
    mockUseRoute.mockReturnValue({
      params: { deal: { ...DEAL, discount_pct: null, reference_price: null } },
    });
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 0,
      recipes: [],
      generated: null,
      error: null,
    });

    await render(<DealDetailScreen />);

    expect(screen.getByText("68,90 kr")).toBeTruthy();
    expect(screen.queryByText("129,00 kr")).toBeNull();
    expect(screen.queryByText("-47%")).toBeNull();
  });

  it("shows an empty state when no recipes come back", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 0,
      recipes: [],
      generated: null,
      error: null,
    });

    await render(<DealDetailScreen />);

    expect(await screen.findByText(/Fant ingen oppskrifter/)).toBeTruthy();
  });

  it("shows an error banner when the request fails", async () => {
    mockedGetRecipes.mockRejectedValueOnce(new ApiError("timeout", "too slow"));

    await render(<DealDetailScreen />);

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
  });
});

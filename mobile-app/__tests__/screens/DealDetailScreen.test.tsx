import { render, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { getRecipesFromIngredients } from "../../src/api/client";
import { ApiError } from "../../src/api/errors";
import { DealDetailScreen } from "../../src/screens/DealDetailScreen";
import type { DiscountedProduct } from "../../src/types/api";

jest.mock("../../src/api/client");

const DEAL: DiscountedProduct = {
  product_name: "Camembert Le Rustique 250g",
  current_price: 68.9,
  reference_price: 129,
  discount_pct: 46.6,
  unit_price: null,
  unit_price_unit: null,
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

  it("requests exactly 1 recipe for the tapped product on initial load", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 1,
      recipes: [{ title: "Cheese Board", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    await render(<DealDetailScreen />);

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledWith([DEAL.product_name], 1, true));
    expect(await screen.findByText("Cheese Board")).toBeTruthy();
  });

  it("shows a 'Show more' button after the initial load and fetches more on tap", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 1,
      recipes: [{ title: "Cheese Board", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    const user = userEvent.setup();
    await render(<DealDetailScreen />);

    expect(await screen.findByText("Cheese Board")).toBeTruthy();
    const showMoreButton = await screen.findByTestId("show-more-button");

    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 2,
      recipes: [
        { title: "Cheese Board", text: "...", rerank_score: null, dense_score: null },
        { title: "Grilled Cheese", text: "...", rerank_score: null, dense_score: null },
      ],
      generated: "...",
      error: null,
    });

    await user.press(showMoreButton);

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledWith([DEAL.product_name], 2, true));
    expect(await screen.findByText("Grilled Cheese")).toBeTruthy();
    expect(screen.getByText("Cheese Board")).toBeTruthy();
  });

  it("hides the 'Show more' button once a request stops returning more recipes", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 1,
      recipes: [{ title: "Cheese Board", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    const user = userEvent.setup();
    await render(<DealDetailScreen />);

    const showMoreButton = await screen.findByTestId("show-more-button");

    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 1,
      recipes: [{ title: "Cheese Board", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    await user.press(showMoreButton);

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId("show-more-button")).toBeNull());
  });

  it("does not show a 'Show more' button when there are no recipes", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: [DEAL.product_name],
      source: "generated",
      count: 0,
      recipes: [],
      generated: null,
      error: null,
    });

    await render(<DealDetailScreen />);

    await screen.findByText(/No recipes found/);
    expect(screen.queryByTestId("show-more-button")).toBeNull();
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

    expect(await screen.findByText(/No recipes found/)).toBeTruthy();
  });

  it("shows an error banner when the request fails", async () => {
    mockedGetRecipes.mockRejectedValueOnce(new ApiError("timeout", "too slow"));

    await render(<DealDetailScreen />);

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
  });
});

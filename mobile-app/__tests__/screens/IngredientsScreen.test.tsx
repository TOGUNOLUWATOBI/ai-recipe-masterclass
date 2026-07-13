import { render, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { getRecipesFromIngredients } from "../../src/api/client";
import { ApiError } from "../../src/api/errors";
import { IngredientsScreen } from "../../src/screens/IngredientsScreen";

jest.mock("../../src/api/client");

const mockedGetRecipes = getRecipesFromIngredients as jest.MockedFunction<typeof getRecipesFromIngredients>;

describe("IngredientsScreen", () => {
  beforeEach(() => {
    mockedGetRecipes.mockReset();
  });

  it("splits comma-separated input into an ingredients array and requests 1 recipe up front", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["chicken", "rice"],
      source: "corpus",
      count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.9 }],
      generated: null,
      error: null,
    });

    const user = userEvent.setup();
    await render(<IngredientsScreen />);
    await user.type(screen.getByTestId("ingredients-input"), "chicken, rice");
    await user.press(screen.getByTestId("ingredients-submit"));

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledTimes(1));
    const [ingredientsArg, maxResultsArg, isGroceryProductArg] = mockedGetRecipes.mock.calls[0];
    expect(ingredientsArg.map((s: string) => s.trim())).toEqual(["chicken", "rice"]);
    expect(maxResultsArg).toBe(1);
    // Free-typed input must never be flagged as a grocery product (omitted here, relying
    // on getRecipesFromIngredients' own default of false) — flagging it would let the
    // backend's Norwegian-heading normalizer corrupt arbitrary English text.
    expect(isGroceryProductArg).toBeUndefined();
    expect(await screen.findByText("Chicken Rice")).toBeTruthy();
  });

  it("shows a 'Show more' button after the first result and re-requests with a larger max_results on tap", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["chicken", "rice"],
      source: "corpus",
      count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.9 }],
      generated: null,
      error: null,
    });

    const user = userEvent.setup();
    await render(<IngredientsScreen />);
    await user.type(screen.getByTestId("ingredients-input"), "chicken, rice");
    await user.press(screen.getByTestId("ingredients-submit"));

    expect(await screen.findByText("Chicken Rice")).toBeTruthy();
    const showMoreButton = await screen.findByTestId("show-more-button");

    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["chicken", "rice"],
      source: "corpus",
      count: 2,
      recipes: [
        { title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.9 },
        { title: "Chicken Fried Rice", text: "...", rerank_score: 1, dense_score: 0.8 },
      ],
      generated: null,
      error: null,
    });

    await user.press(showMoreButton);

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledTimes(2));
    const [, maxResultsArg, isGroceryProductArg] = mockedGetRecipes.mock.calls[1];
    expect(maxResultsArg).toBe(2);
    expect(isGroceryProductArg).toBeUndefined();
    expect(await screen.findByText("Chicken Fried Rice")).toBeTruthy();
    expect(screen.getByText("Chicken Rice")).toBeTruthy();
  });

  it("hides the 'Show more' button once a request stops returning more recipes", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["chicken"],
      source: "corpus",
      count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.9 }],
      generated: null,
      error: null,
    });

    const user = userEvent.setup();
    await render(<IngredientsScreen />);
    await user.type(screen.getByTestId("ingredients-input"), "chicken");
    await user.press(screen.getByTestId("ingredients-submit"));

    const showMoreButton = await screen.findByTestId("show-more-button");

    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["chicken"],
      source: "corpus",
      count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.9 }],
      generated: null,
      error: null,
    });

    await user.press(showMoreButton);

    await waitFor(() => expect(mockedGetRecipes).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId("show-more-button")).toBeNull());
  });

  it("shows the corpus-match count when source is corpus", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["chicken"],
      source: "corpus",
      count: 2,
      recipes: [
        { title: "A", text: "...", rerank_score: 1, dense_score: 0.9 },
        { title: "B", text: "...", rerank_score: 1, dense_score: 0.9 },
      ],
      generated: null,
      error: null,
    });

    const user = userEvent.setup();
    await render(<IngredientsScreen />);
    await user.type(screen.getByTestId("ingredients-input"), "chicken");
    await user.press(screen.getByTestId("ingredients-submit"));

    expect(await screen.findByText(/Found 2 matching recipes/)).toBeTruthy();
  });

  it("shows the generated-suggestion count when source is generated", async () => {
    mockedGetRecipes.mockResolvedValueOnce({
      ingredients: ["sea cucumber"],
      source: "generated",
      count: 1,
      recipes: [{ title: "Sea Cucumber Soup", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    const user = userEvent.setup();
    await render(<IngredientsScreen />);
    await user.type(screen.getByTestId("ingredients-input"), "sea cucumber");
    await user.press(screen.getByTestId("ingredients-submit"));

    expect(await screen.findByText(/1 generated suggestion/)).toBeTruthy();
  });

  it("shows an error banner on failure", async () => {
    mockedGetRecipes.mockRejectedValueOnce(new ApiError("timeout", "too slow"));

    const user = userEvent.setup();
    await render(<IngredientsScreen />);
    await user.type(screen.getByTestId("ingredients-input"), "chicken");
    await user.press(screen.getByTestId("ingredients-submit"));

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
  });
});

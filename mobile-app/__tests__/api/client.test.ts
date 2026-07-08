import { askQuestion, getDiscountedRecipes, getRecipesFromIngredients } from "../../src/api/client";
import { ApiError } from "../../src/api/errors";
import { ValidationError } from "../../src/api/validation";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok,
    status,
    json: async () => body,
  });
}

describe("askQuestion", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("sends the sanitized question and returns the parsed response", async () => {
    mockFetchOnce({
      question: "jollof rice",
      retrieved: [],
      grounded: [{ id: 1, score: 0.9, payload: { title: "Jollof Rice" }, text: "..." }],
      context: "...",
      answer: "### Jollof Rice",
      error: null,
      elapsed: 1.2,
    });

    const result = await askQuestion("  jollof rice  ");

    expect(result.answer).toBe("### Jollof Rice");
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({ question: "jollof rice" });
  });

  it("rejects an empty question before making any network call", async () => {
    await expect(askQuestion("   ")).rejects.toThrow(ValidationError);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("throws ApiError('http', ...) on a non-2xx response", async () => {
    mockFetchOnce({}, false, 500);
    await expect(askQuestion("test")).rejects.toMatchObject({ kind: "http", statusCode: 500 });
  });

  it("throws ApiError('network', ...) when fetch rejects", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(askQuestion("test")).rejects.toMatchObject({ kind: "network" });
  });

  it("throws ApiError('timeout', ...) when the request is aborted", async () => {
    const abortError = new Error("Aborted");
    abortError.name = "AbortError";
    (global.fetch as jest.Mock).mockRejectedValueOnce(abortError);
    await expect(askQuestion("test")).rejects.toMatchObject({ kind: "timeout" });
  });

  it("throws ApiError('invalid_response', ...) when JSON parsing fails", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("not json");
      },
    });
    await expect(askQuestion("test")).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws ApiError('invalid_response', ...) when required fields are missing", async () => {
    mockFetchOnce({ answer: "something" }); // missing "question" and "grounded"
    await expect(askQuestion("test")).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("getRecipesFromIngredients", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("sanitizes ingredients and caps max_results before sending", async () => {
    mockFetchOnce({
      ingredients: ["chicken", "rice"],
      source: "corpus",
      count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.8 }],
      generated: null,
      error: null,
    });

    await getRecipesFromIngredients([" chicken ", "", "rice"], 999);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.ingredients).toEqual(["chicken", "rice"]);
    expect(body.max_results).toBeLessThanOrEqual(20); // MAX_INGREDIENT_COUNT
  });

  it("rejects an all-empty ingredients list before any network call", async () => {
    await expect(getRecipesFromIngredients(["", "  "])).rejects.toThrow(ValidationError);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("throws ApiError('invalid_response', ...) when recipes field is malformed", async () => {
    mockFetchOnce({ ingredients: ["chicken"], source: "corpus", count: 1, recipes: "not an array", generated: null, error: null });
    await expect(getRecipesFromIngredients(["chicken"])).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("getDiscountedRecipes", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("returns the parsed response on success", async () => {
    mockFetchOnce({
      discounted_ingredients: [
        {
          category: "Ost", product_name: "Camembert", current_price: 68.9, reference_price: 129,
          discount_pct: 46.6, unit_price: null, image_url: null, store_name: "Coop", store_logo_url: null,
        },
      ],
      source: "generated",
      count: 1,
      recipes: [{ title: "Camembert", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
      updated_at: "2026-07-08T09:19:17.306962+00:00",
    });

    const result = await getDiscountedRecipes(5);
    expect(result.discounted_ingredients).toHaveLength(1);
    expect(result.discounted_ingredients[0].product_name).toBe("Camembert");
    expect(result.updated_at).toBe("2026-07-08T09:19:17.306962+00:00");
  });

  it("defaults to include_recipes=true, and passes include_recipes=false when asked for the fast path", async () => {
    mockFetchOnce({
      discounted_ingredients: [], source: null, count: 0, recipes: [], generated: null, error: null, updated_at: null,
    });
    await getDiscountedRecipes(5);
    let [url] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain("include_recipes=true");

    mockFetchOnce({
      discounted_ingredients: [], source: null, count: 0, recipes: [], generated: null, error: null, updated_at: null,
    });
    await getDiscountedRecipes(5, false);
    [url] = (global.fetch as jest.Mock).mock.calls[1];
    expect(url).toContain("include_recipes=false");
  });

  it("throws ApiError('invalid_response', ...) when discounted_ingredients is missing", async () => {
    mockFetchOnce({ source: null, count: 0, recipes: [], generated: null, error: null });
    await expect(getDiscountedRecipes()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("surfaces a backend-reported error without throwing (caller checks response.error)", async () => {
    mockFetchOnce({
      discounted_ingredients: [],
      source: null,
      count: 0,
      recipes: [],
      generated: null,
      error: "KASSALAPP_API_KEY not configured",
    });
    const result = await getDiscountedRecipes();
    expect(result.error).toBe("KASSALAPP_API_KEY not configured");
  });
});

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError("network", "test message");
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("test message");
  });
});

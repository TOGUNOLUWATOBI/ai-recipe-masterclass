import {
  askQuestion,
  getDiscountedRecipes,
  getIngredientOffers,
  getMealIdeasFromCart,
  getMealIdeasFromStore,
  getRecipesFromIngredients,
  submitMealIdeaFeedback,
} from "../../src/api/client";
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
    expect(JSON.parse(options.body)).toEqual({ question: "jollof rice", language: "en" });
  });

  it("sends the selected language", async () => {
    mockFetchOnce({
      question: "hva kan jeg lage med kylling?",
      retrieved: [],
      grounded: [],
      context: "...",
      answer: "### Kylling og ris",
      error: null,
      elapsed: 1.2,
    });

    await askQuestion("hva kan jeg lage med kylling?", "no");

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(JSON.parse(options.body).language).toBe("no");
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

  it("defaults is_grocery_product to false when not specified", async () => {
    mockFetchOnce({
      ingredients: ["chicken"],
      source: "corpus",
      count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.8 }],
      generated: null,
      error: null,
    });

    await getRecipesFromIngredients(["chicken"]);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.is_grocery_product).toBe(false);
  });

  it("sends is_grocery_product: true when explicitly requested", async () => {
    mockFetchOnce({
      ingredients: ["COOP GRILL PERFEKT BOKEROKTE SOMMERKOTELETTER"],
      source: "generated",
      count: 1,
      recipes: [{ title: "Grillkoteletter", text: "...", rerank_score: null, dense_score: null }],
      generated: "...",
      error: null,
    });

    await getRecipesFromIngredients(["COOP GRILL PERFEKT BOKEROKTE SOMMERKOTELETTER"], 1, true);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.is_grocery_product).toBe(true);
  });

  it("sends the selected language, defaulting to English", async () => {
    mockFetchOnce({
      ingredients: ["chicken"], source: "corpus", count: 1,
      recipes: [{ title: "Chicken Rice", text: "...", rerank_score: 1, dense_score: 0.8 }],
      generated: null, error: null,
    });
    await getRecipesFromIngredients(["chicken"]);
    let body = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body);
    expect(body.language).toBe("en");

    mockFetchOnce({
      ingredients: ["kylling"], source: "corpus", count: 1,
      recipes: [{ title: "Kylling og ris", text: "...", rerank_score: 1, dense_score: 0.8 }],
      generated: null, error: null,
    });
    await getRecipesFromIngredients(["kylling"], 10, false, "no");
    body = JSON.parse((global.fetch as jest.Mock).mock.calls[1][1].body);
    expect(body.language).toBe("no");
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
          product_name: "Camembert", current_price: 68.9, reference_price: 129,
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

  it("defaults to language=en, and passes the selected language when given", async () => {
    mockFetchOnce({
      discounted_ingredients: [], source: null, count: 0, recipes: [], generated: null, error: null, updated_at: null,
    });
    await getDiscountedRecipes(5);
    let [url] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain("language=en");

    mockFetchOnce({
      discounted_ingredients: [], source: null, count: 0, recipes: [], generated: null, error: null, updated_at: null,
    });
    await getDiscountedRecipes(5, true, "no");
    [url] = (global.fetch as jest.Mock).mock.calls[1];
    expect(url).toContain("language=no");
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
      error: "discount cache not available",
    });
    const result = await getDiscountedRecipes();
    expect(result.error).toBe("discount cache not available");
  });
});

describe("getMealIdeasFromCart", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts discount_item_ids/max_results/language and returns the parsed response", async () => {
    mockFetchOnce({ ideas: [], excluded_cart_items: [], source: null });

    const result = await getMealIdeasFromCart(["Kiwi::Kyllingfilet"], 3, "no");

    const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain("/meal-ideas/from-cart");
    expect(JSON.parse(options.body)).toEqual({
      discount_item_ids: ["Kiwi::Kyllingfilet"],
      max_results: 3,
      language: "no",
    });
    expect(result.ideas).toEqual([]);
  });

  it("throws ApiError('invalid_response', ...) when ideas is missing", async () => {
    mockFetchOnce({ excluded_cart_items: [], source: null });
    await expect(getMealIdeasFromCart(["Kiwi::X"])).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("getMealIdeasFromStore", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts store_name/max_results/language and returns the parsed response", async () => {
    mockFetchOnce({ ideas: [], excluded_store_items: [], store_name: "Kiwi", source: null });

    const result = await getMealIdeasFromStore("Kiwi", 3, "no");

    const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain("/meal-ideas/from-store");
    expect(JSON.parse(options.body)).toEqual({ store_name: "Kiwi", max_results: 3, language: "no" });
    expect(result.store_name).toBe("Kiwi");
  });

  it("throws ApiError('invalid_response', ...) when excluded_store_items is missing", async () => {
    mockFetchOnce({ ideas: [], store_name: "Kiwi", source: null });
    await expect(getMealIdeasFromStore("Kiwi")).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("getIngredientOffers", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts ingredients/max_offers_per_ingredient and returns the parsed response", async () => {
    mockFetchOnce({ snapshot_updated_at: "2026-07-16T05:00:00Z", ingredients: [{ ingredient: "chicken fillet", offers: [] }] });

    const result = await getIngredientOffers(["chicken fillet"], 2);

    const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain("/ingredient-offers");
    expect(JSON.parse(options.body)).toEqual({ ingredients: ["chicken fillet"], max_offers_per_ingredient: 2 });
    expect(result.ingredients).toHaveLength(1);
  });

  it("defaults max_offers_per_ingredient to 3", async () => {
    mockFetchOnce({ snapshot_updated_at: null, ingredients: [] });

    await getIngredientOffers(["chicken fillet"]);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(JSON.parse(options.body).max_offers_per_ingredient).toBe(3);
  });

  it("throws ApiError('invalid_response', ...) when ingredients is missing", async () => {
    mockFetchOnce({ snapshot_updated_at: null });
    await expect(getIngredientOffers(["chicken fillet"])).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("submitMealIdeaFeedback", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("posts the feedback payload with the given fields", async () => {
    mockFetchOnce({ status: "ok" });

    await submitMealIdeaFeedback(
      "req-abc", "cart", "Chicken and Rice", false,
      ["too_complicated"], ["chicken fillet"], ["rice"], "retrieved"
    );

    const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain("/meal-ideas/feedback");
    expect(JSON.parse(options.body)).toEqual({
      request_id: "req-abc",
      recommendation_type: "cart",
      idea_title: "Chicken and Rice",
      helpful: false,
      reasons: ["too_complicated"],
      selected_items_used: ["chicken fillet"],
      missing_required_ingredients: ["rice"],
      source_type: "retrieved",
    });
  });

  it("defaults reasons/selected/missing to empty arrays and source_type to null", async () => {
    mockFetchOnce({ status: "ok" });

    await submitMealIdeaFeedback("req-abc", "store", "Ribbe", true);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      request_id: "req-abc",
      recommendation_type: "store",
      idea_title: "Ribbe",
      helpful: true,
      reasons: [],
      selected_items_used: [],
      missing_required_ingredients: [],
      source_type: null,
    });
  });

  it("never throws when the request fails -- best-effort only", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network down"));

    await expect(submitMealIdeaFeedback("req-abc", "cart", "Chicken and Rice", true)).resolves.toBeUndefined();
  });

  it("never throws on a non-2xx response", async () => {
    mockFetchOnce({}, false, 500);

    await expect(submitMealIdeaFeedback("req-abc", "cart", "Chicken and Rice", true)).resolves.toBeUndefined();
  });
});

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError("network", "test message");
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("test message");
  });
});

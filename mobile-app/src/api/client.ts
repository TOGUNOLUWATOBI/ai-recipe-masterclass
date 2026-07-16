import { API_BASE_URL, DEFAULT_TIMEOUT_MS, DISCOUNTED_TIMEOUT_MS } from "../config";
import type { Language } from "../i18n/language";
import type { DiscountedResponse, GeneratedRecipe, IngredientsResponse, QueryResponse } from "../types/api";
import { ApiError } from "./errors";
import { MAX_INGREDIENT_COUNT, sanitizeIngredients, sanitizeQuestion } from "./validation";

/** Generic fetch wrapper: enforces HTTPS + the fixed base URL, a hard timeout (LLM
 * calls can hang far longer than a typical API without one), and turns every failure
 * mode (network down, timeout, non-2xx status, malformed JSON) into a typed ApiError
 * instead of letting a raw fetch/parse exception reach the UI layer unclassified. */
async function fetchJson<T>(path: string, options: RequestInit, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError("timeout", "Request timed out");
    }
    throw new ApiError("network", err instanceof Error ? err.message : "Network request failed");
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    throw new ApiError("http", `Request failed with status ${response.status}`, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("invalid_response", "Server response was not valid JSON");
  }
}

function isRecipeArray(value: unknown): value is GeneratedRecipe[] {
  return Array.isArray(value) && value.every((item) => typeof item === "object" && item !== null && "text" in item);
}

export async function askQuestion(question: string, language: Language = "en"): Promise<QueryResponse> {
  const sanitized = sanitizeQuestion(question);
  const data = await fetchJson<QueryResponse>(
    "/query",
    { method: "POST", body: JSON.stringify({ question: sanitized, language }) },
    DEFAULT_TIMEOUT_MS
  );

  if (typeof data.question !== "string" || !Array.isArray(data.grounded)) {
    throw new ApiError("invalid_response", "Query response was missing expected fields");
  }
  return data;
}

export async function getRecipesFromIngredients(
  ingredients: string[],
  maxResults = 10,
  isGroceryProduct: boolean = false,
  language: Language = "en"
): Promise<IngredientsResponse> {
  const sanitized = sanitizeIngredients(ingredients);
  const cappedResults = Math.max(1, Math.min(maxResults, MAX_INGREDIENT_COUNT));
  const data = await fetchJson<IngredientsResponse>(
    "/recipes/from-ingredients",
    {
      method: "POST",
      body: JSON.stringify({
        ingredients: sanitized,
        max_results: cappedResults,
        is_grocery_product: isGroceryProduct,
        language,
      }),
    },
    DEFAULT_TIMEOUT_MS
  );

  if (!isRecipeArray(data.recipes)) {
    throw new ApiError("invalid_response", "Ingredients response was missing expected fields");
  }
  return data;
}

export async function getDiscountedRecipes(
  maxResults = 10,
  includeRecipes = true,
  language: Language = "en"
): Promise<DiscountedResponse> {
  const cappedResults = Math.max(1, Math.min(maxResults, MAX_INGREDIENT_COUNT));
  // The discount list itself comes from a cache the backend refreshes on a daily cron
  // job (not a live API call per request), so this is fast regardless —
  // includeRecipes=false additionally skips the LLM generation pass (and so the
  // language param has no effect) for callers that only need the browsable deal list
  // right now (see StoresScreen).
  const data = await fetchJson<DiscountedResponse>(
    `/recipes/discounted?max_results=${cappedResults}&include_recipes=${includeRecipes}&language=${language}`,
    { method: "GET" },
    includeRecipes ? DISCOUNTED_TIMEOUT_MS : DEFAULT_TIMEOUT_MS
  );

  if (!Array.isArray(data.discounted_ingredients) || !isRecipeArray(data.recipes)) {
    throw new ApiError("invalid_response", "Discounted response was missing expected fields");
  }
  return data;
}

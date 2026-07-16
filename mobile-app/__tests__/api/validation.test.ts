import {
  MAX_INGREDIENT_COUNT,
  MAX_INGREDIENT_LENGTH,
  MAX_QUESTION_LENGTH,
  sanitizeIngredients,
  sanitizeQuestion,
  ValidationError,
} from "../../src/api/validation";
import { DEFAULT_LANGUAGE, setLanguage } from "../../src/i18n/language";

describe("sanitizeQuestion", () => {
  it("trims whitespace", () => {
    expect(sanitizeQuestion("  jollof rice  ")).toBe("jollof rice");
  });

  it("collapses internal whitespace", () => {
    expect(sanitizeQuestion("jollof    rice")).toBe("jollof rice");
  });

  it("rejects an empty question", () => {
    expect(() => sanitizeQuestion("")).toThrow(ValidationError);
    expect(() => sanitizeQuestion("   ")).toThrow(ValidationError);
  });

  it("rejects a question over the max length", () => {
    const tooLong = "a".repeat(MAX_QUESTION_LENGTH + 1);
    expect(() => sanitizeQuestion(tooLong)).toThrow(ValidationError);
  });

  it("accepts a question exactly at the max length", () => {
    const exact = "a".repeat(MAX_QUESTION_LENGTH);
    expect(sanitizeQuestion(exact)).toBe(exact);
  });
});

describe("sanitizeIngredients", () => {
  it("trims and filters empty entries", () => {
    expect(sanitizeIngredients([" chicken ", "", "  ", "rice"])).toEqual(["chicken", "rice"]);
  });

  it("rejects an empty list after filtering", () => {
    expect(() => sanitizeIngredients(["", "  ", ""])).toThrow(ValidationError);
  });

  it("rejects an empty array", () => {
    expect(() => sanitizeIngredients([])).toThrow(ValidationError);
  });

  it("rejects more than the max ingredient count", () => {
    const tooMany = Array.from({ length: MAX_INGREDIENT_COUNT + 1 }, (_, i) => `item${i}`);
    expect(() => sanitizeIngredients(tooMany)).toThrow(ValidationError);
  });

  it("accepts exactly the max ingredient count", () => {
    const exact = Array.from({ length: MAX_INGREDIENT_COUNT }, (_, i) => `item${i}`);
    expect(sanitizeIngredients(exact)).toHaveLength(MAX_INGREDIENT_COUNT);
  });

  it("rejects an ingredient over the max length", () => {
    const tooLong = "a".repeat(MAX_INGREDIENT_LENGTH + 1);
    expect(() => sanitizeIngredients([tooLong])).toThrow(ValidationError);
  });

  it("collapses internal whitespace per ingredient", () => {
    expect(sanitizeIngredients(["chicken   breast"])).toEqual(["chicken breast"]);
  });
});

describe("validation messages respect the app language", () => {
  afterEach(() => {
    setLanguage(DEFAULT_LANGUAGE);
  });

  it("throws Norwegian messages when the app language is Norwegian", () => {
    setLanguage("no");

    expect(() => sanitizeQuestion("")).toThrow("Skriv inn et spørsmål.");
    expect(() => sanitizeIngredients([])).toThrow("Skriv inn minst én ingrediens.");
  });
});

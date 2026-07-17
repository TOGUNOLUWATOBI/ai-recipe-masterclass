import { translations } from "../../src/i18n/translations";

describe("translations", () => {
  it("has the exact same set of keys in every language", () => {
    // Regression guard against translation drift -- a key added to one language and
    // forgotten in the other would otherwise only surface as a silent `undefined` (or
    // a missing function) the first time that string renders in the other language.
    const enKeys = Object.keys(translations.en).sort();
    const noKeys = Object.keys(translations.no).sort();
    expect(noKeys).toEqual(enKeys);
  });

  it("has a non-empty string (or a function) for every English value", () => {
    for (const value of Object.values(translations.en)) {
      if (typeof value === "function") continue;
      expect(typeof value).toBe("string");
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  it("has a non-empty string (or a function) for every Norwegian value", () => {
    for (const value of Object.values(translations.no)) {
      if (typeof value === "function") continue;
      expect(typeof value).toBe("string");
      expect((value as string).length).toBeGreaterThan(0);
    }
  });

  it("pluralizes the meal-idea selection count correctly in both languages", () => {
    expect(translations.en.ingredientsSelectedForMealIdeas(1)).toBe("1 ingredient selected for meal ideas");
    expect(translations.en.ingredientsSelectedForMealIdeas(2)).toBe("2 ingredients selected for meal ideas");
    expect(translations.no.ingredientsSelectedForMealIdeas(1)).toBe("1 ingrediens valgt til middagsidéer");
    expect(translations.no.ingredientsSelectedForMealIdeas(2)).toBe("2 ingredienser valgt til middagsidéer");
  });
});

import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { RecipeCard } from "../../src/components/RecipeCard";
import { LanguageToggle } from "../../src/components/LanguageToggle";
import { renderWithProviders } from "../../test-utils/testUtils";

const RECIPE_TEXT = "### Chicken Rice\n\n**Ingredients:**\nchicken, rice\n\n**Instructions:**\nCook it.";

function RecipeCardWithToggle() {
  return (
    <>
      <LanguageToggle />
      <RecipeCard text={RECIPE_TEXT} />
    </>
  );
}

describe("RecipeCard", () => {
  it("shows English section labels by default", async () => {
    await renderWithProviders(<RecipeCard text={RECIPE_TEXT} />);

    expect(screen.getByText("Ingredients")).toBeTruthy();
    expect(screen.getByText("Instructions")).toBeTruthy();
  });

  it("switches its own section labels to Norwegian when the language toggle is set to NO", async () => {
    // The recipe TEXT itself is already translated server-side by the time it
    // reaches this component (see src/rag/translator.py) -- RecipeCard only ever
    // translates its own two section labels, never recipe content, which is why
    // this test uses plain English RECIPE_TEXT throughout.
    const user = userEvent.setup();
    await renderWithProviders(<RecipeCardWithToggle />);
    expect(screen.getByText("Ingredients")).toBeTruthy();

    await user.press(screen.getByTestId("language-toggle-no"));

    expect(screen.getByText("Ingredienser")).toBeTruthy();
    expect(screen.getByText("Instruksjoner")).toBeTruthy();
  });
});

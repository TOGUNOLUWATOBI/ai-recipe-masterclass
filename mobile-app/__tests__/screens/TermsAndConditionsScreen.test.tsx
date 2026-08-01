import { screen } from "@testing-library/react-native";
import React from "react";
import { TermsAndConditionsScreen } from "../../src/screens/TermsAndConditionsScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

describe("TermsAndConditionsScreen", () => {
  it("renders terms content in English by default", async () => {
    await renderWithProviders(<TermsAndConditionsScreen />);

    expect(screen.getByTestId("terms-and-conditions-screen")).toBeTruthy();
    expect(screen.getByText("Acceptance of terms")).toBeTruthy();
    expect(screen.getByText("AI-generated recipes")).toBeTruthy();
    expect(screen.getByText("No guarantee of price or availability")).toBeTruthy();
  });
});

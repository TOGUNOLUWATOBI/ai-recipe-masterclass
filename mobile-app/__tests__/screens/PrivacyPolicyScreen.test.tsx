import { screen } from "@testing-library/react-native";
import React from "react";
import { PrivacyPolicyScreen } from "../../src/screens/PrivacyPolicyScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

describe("PrivacyPolicyScreen", () => {
  it("renders policy content in English by default", async () => {
    await renderWithProviders(<PrivacyPolicyScreen />);

    expect(screen.getByTestId("privacy-policy-screen")).toBeTruthy();
    expect(screen.getByText("What data do we collect?")).toBeTruthy();
    expect(screen.getByText("Your rights")).toBeTruthy();
  });
});

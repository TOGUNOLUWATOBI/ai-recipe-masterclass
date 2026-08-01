import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { TermsGateScreen } from "../../src/screens/TermsGateScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

describe("TermsGateScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  it("shows the app name and motto", async () => {
    await renderWithProviders(<TermsGateScreen />);

    expect(screen.getByText("Matty")).toBeTruthy();
    expect(screen.getByText("Welcome to a cheaper everyday")).toBeTruthy();
  });

  it("navigates to Terms & Conditions when that link is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<TermsGateScreen />);

    await user.press(screen.getByTestId("terms-gate-terms-link"));

    expect(mockNavigate).toHaveBeenCalledWith("TermsAndConditions");
  });

  it("navigates to Privacy Policy when that link is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<TermsGateScreen />);

    await user.press(screen.getByTestId("terms-gate-privacy-link"));

    expect(mockNavigate).toHaveBeenCalledWith("PrivacyPolicy");
  });

  it("accepting does not itself navigate -- AppNavigator reacts to the state change instead", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<TermsGateScreen />);

    await user.press(screen.getByTestId("terms-gate-accept-button"));

    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { SettingsScreen } from "../../src/screens/SettingsScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

describe("SettingsScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  afterEach(async () => {
    await AsyncStorage.clear();
  });

  it("navigates to Terms & Conditions when that link is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<SettingsScreen />);

    await user.press(screen.getByTestId("settings-terms-link"));

    expect(mockNavigate).toHaveBeenCalledWith("TermsAndConditions");
  });

  it("navigates to Privacy Policy when that link is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<SettingsScreen />);

    await user.press(screen.getByTestId("settings-privacy-policy-link"));

    expect(mockNavigate).toHaveBeenCalledWith("PrivacyPolicy");
  });

  it("delete my data asks for confirmation and only clears the cart on confirm", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([{ cart_item_id: "x" }]));
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const user = userEvent.setup();
    await renderWithProviders(<SettingsScreen />);

    await user.press(screen.getByTestId("delete-my-data-button"));

    expect(alertSpy).toHaveBeenCalledTimes(1);
    const buttons = alertSpy.mock.calls[0][2] as { text: string; style?: string; onPress?: () => void }[];
    const confirmButton = buttons.find((b) => b.style === "destructive");

    await act(async () => {
      confirmButton?.onPress?.();
    });

    await waitFor(async () => expect(await AsyncStorage.getItem("cart")).toBe("[]"));
    alertSpy.mockRestore();
  });

  it("does not clear the cart when the confirmation is dismissed", async () => {
    await AsyncStorage.setItem("cart", JSON.stringify([{ cart_item_id: "x" }]));
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const user = userEvent.setup();
    await renderWithProviders(<SettingsScreen />);

    await user.press(screen.getByTestId("delete-my-data-button"));

    expect(alertSpy).toHaveBeenCalledTimes(1);
    // Never invoking any button's onPress simulates dismissing the alert -- the cart
    // must be untouched.
    expect(await AsyncStorage.getItem("cart")).toBe(JSON.stringify([{ cart_item_id: "x" }]));
    alertSpy.mockRestore();
  });
});

import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";
import { HomeScreen } from "../../src/screens/HomeScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

const SESSION = {
  access_token: "abc", refresh_token: "def", expires_in: 3600, token_type: "bearer", phone: "+4791234567",
};

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

describe("HomeScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  afterEach(async () => {
    await AsyncStorage.clear();
  });

  it("shows the app name and motto", async () => {
    await renderWithProviders(<HomeScreen />);

    expect(screen.getByText("AI Recipe Masterclass")).toBeTruthy();
    expect(screen.getByText("Welcome to a cheaper everyday")).toBeTruthy();
  });

  it("navigates to the Deals tab when 'Dagens Deals' is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<HomeScreen />);

    await user.press(screen.getByTestId("dagens-deals-button"));

    expect(mockNavigate).toHaveBeenCalledWith("Tilbud");
  });

  it("shows all 4 nav buttons and navigates to the right tab for each", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<HomeScreen />);

    await user.press(screen.getByTestId("home-nav-Tilbud"));
    expect(mockNavigate).toHaveBeenCalledWith("Tilbud");

    await user.press(screen.getByTestId("home-nav-Cart"));
    expect(mockNavigate).toHaveBeenCalledWith("Cart");

    await user.press(screen.getByTestId("home-nav-Ask"));
    expect(mockNavigate).toHaveBeenCalledWith("Ask");

    await user.press(screen.getByTestId("home-nav-MealIdeas"));
    expect(mockNavigate).toHaveBeenCalledWith("MealIdeas");
  });

  describe("account section", () => {
    it("shows a login button when logged out, and navigates to Login when pressed", async () => {
      const user = userEvent.setup();
      await renderWithProviders(<HomeScreen />);

      expect(screen.queryByTestId("logout-button")).toBeNull();
      await user.press(screen.getByTestId("login-button"));

      expect(mockNavigate).toHaveBeenCalledWith("Login");
    });

    it("shows the phone number, log out, and delete-my-data actions when logged in", async () => {
      await AsyncStorage.setItem("auth_session", JSON.stringify(SESSION));

      await renderWithProviders(<HomeScreen />);

      expect(await screen.findByTestId("logout-button")).toBeTruthy();
      expect(screen.getByTestId("delete-my-data-button")).toBeTruthy();
      expect(screen.queryByTestId("login-button")).toBeNull();
      expect(screen.getByText(/\+4791234567/)).toBeTruthy();
    });

    it("log out returns to the logged-out state", async () => {
      await AsyncStorage.setItem("auth_session", JSON.stringify(SESSION));
      const user = userEvent.setup();
      await renderWithProviders(<HomeScreen />);
      await screen.findByTestId("logout-button");

      await user.press(screen.getByTestId("logout-button"));

      expect(await screen.findByTestId("login-button")).toBeTruthy();
    });

    it("delete my data asks for confirmation and only clears on confirm", async () => {
      await AsyncStorage.setItem("auth_session", JSON.stringify(SESSION));
      await AsyncStorage.setItem("cart", JSON.stringify([{ cart_item_id: "x" }]));
      const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
      const user = userEvent.setup();
      await renderWithProviders(<HomeScreen />);
      await screen.findByTestId("delete-my-data-button");

      await user.press(screen.getByTestId("delete-my-data-button"));

      expect(alertSpy).toHaveBeenCalledTimes(1);
      const buttons = alertSpy.mock.calls[0][2] as { text: string; style?: string; onPress?: () => void }[];
      const confirmButton = buttons.find((b) => b.style === "destructive");

      await act(async () => {
        confirmButton?.onPress?.();
      });

      expect(await screen.findByTestId("login-button")).toBeTruthy();
      await waitFor(async () => expect(await AsyncStorage.getItem("auth_session")).toBeNull());
      await waitFor(async () => expect(await AsyncStorage.getItem("cart")).toBe("[]"));
      alertSpy.mockRestore();
    });
  });
});

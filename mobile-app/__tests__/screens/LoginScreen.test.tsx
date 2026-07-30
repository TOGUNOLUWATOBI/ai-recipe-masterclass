import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { LoginScreen } from "../../src/screens/LoginScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate }),
  };
});

const mockSendCode = jest.fn();
jest.mock("../../src/auth/AuthContext", () => ({
  // renderWithProviders (test-utils/testUtils.tsx) also wraps every screen in the
  // real AuthProvider -- since this mock replaces the whole module, it must provide
  // a stand-in for that too, or AuthProvider resolves to undefined and rendering
  // crashes with "Element type is invalid" before the test itself even runs.
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({ sendCode: mockSendCode }),
}));

describe("LoginScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockSendCode.mockReset();
  });

  it("refuses to send a code without agreeing to the Privacy Policy", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<LoginScreen />);

    await user.type(screen.getByTestId("phone-input"), "91234567");
    await user.press(screen.getByTestId("send-code-button"));

    expect(await screen.findByTestId("error-banner")).toHaveTextContent(/Privacy Policy/);
    expect(mockSendCode).not.toHaveBeenCalled();
  });

  it("refuses to send a code for too short a phone number, even with consent given", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<LoginScreen />);

    await user.press(screen.getByTestId("consent-checkbox"));
    await user.type(screen.getByTestId("phone-input"), "123");
    await user.press(screen.getByTestId("send-code-button"));

    expect(await screen.findByTestId("error-banner")).toHaveTextContent(/valid phone number/);
    expect(mockSendCode).not.toHaveBeenCalled();
  });

  it("sends the code with the default Norway dial code and navigates to verify", async () => {
    mockSendCode.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    await renderWithProviders(<LoginScreen />);

    await user.press(screen.getByTestId("consent-checkbox"));
    await user.type(screen.getByTestId("phone-input"), "91234567");
    await user.press(screen.getByTestId("send-code-button"));

    expect(mockSendCode).toHaveBeenCalledWith("+4791234567");
    expect(mockNavigate).toHaveBeenCalledWith("VerifyOtp", { phone: "+4791234567" });
  });

  it("strips non-digit characters from the phone number before sending", async () => {
    mockSendCode.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    await renderWithProviders(<LoginScreen />);

    await user.press(screen.getByTestId("consent-checkbox"));
    await user.type(screen.getByTestId("phone-input"), "912 34 567");
    await user.press(screen.getByTestId("send-code-button"));

    expect(mockSendCode).toHaveBeenCalledWith("+4791234567");
  });

  it("shows an error banner and does not navigate when sendCode fails", async () => {
    mockSendCode.mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    await renderWithProviders(<LoginScreen />);

    await user.press(screen.getByTestId("consent-checkbox"));
    await user.type(screen.getByTestId("phone-input"), "91234567");
    await user.press(screen.getByTestId("send-code-button"));

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("navigates to the Privacy Policy screen when the link is pressed", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<LoginScreen />);

    await user.press(screen.getByText("Privacy Policy"));

    expect(mockNavigate).toHaveBeenCalledWith("PrivacyPolicy");
  });
});

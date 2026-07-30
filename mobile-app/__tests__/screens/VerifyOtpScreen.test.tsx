import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { VerifyOtpScreen } from "../../src/screens/VerifyOtpScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

const mockNavigate = jest.fn();
const mockPopToTop = jest.fn();
let mockRouteParams = { phone: "+4791234567" };
jest.mock("@react-navigation/native", () => {
  const actual = jest.requireActual("@react-navigation/native");
  return {
    ...actual,
    useNavigation: () => ({ navigate: mockNavigate, popToTop: mockPopToTop }),
    useRoute: () => ({ params: mockRouteParams }),
  };
});

const mockVerifyCode = jest.fn();
const mockSendCode = jest.fn();
jest.mock("../../src/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({ verifyCode: mockVerifyCode, sendCode: mockSendCode }),
}));

describe("VerifyOtpScreen", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockPopToTop.mockReset();
    mockVerifyCode.mockReset();
    mockSendCode.mockReset();
    mockRouteParams = { phone: "+4791234567" };
  });

  it("shows the phone number the code was sent to", async () => {
    await renderWithProviders(<VerifyOtpScreen />);

    expect(screen.getByText(/\+4791234567/)).toBeTruthy();
  });

  it("refuses to verify a code that isn't 6 digits", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<VerifyOtpScreen />);

    await user.type(screen.getByTestId("otp-input"), "123");
    await user.press(screen.getByTestId("verify-code-button"));

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
    expect(mockVerifyCode).not.toHaveBeenCalled();
  });

  it("verifies the code and returns to the top of the stack on success", async () => {
    mockVerifyCode.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    await renderWithProviders(<VerifyOtpScreen />);

    await user.type(screen.getByTestId("otp-input"), "123456");
    await user.press(screen.getByTestId("verify-code-button"));

    expect(mockVerifyCode).toHaveBeenCalledWith("+4791234567", "123456");
    expect(mockPopToTop).toHaveBeenCalled();
  });

  it("shows an error banner and does not navigate when the code is wrong", async () => {
    mockVerifyCode.mockRejectedValueOnce(new Error("invalid code"));
    const user = userEvent.setup();
    await renderWithProviders(<VerifyOtpScreen />);

    await user.type(screen.getByTestId("otp-input"), "000000");
    await user.press(screen.getByTestId("verify-code-button"));

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
    expect(mockPopToTop).not.toHaveBeenCalled();
  });

  it("resends the code to the same phone number", async () => {
    mockSendCode.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    await renderWithProviders(<VerifyOtpScreen />);

    await user.press(screen.getByTestId("resend-code-button"));

    expect(mockSendCode).toHaveBeenCalledWith("+4791234567");
  });
});

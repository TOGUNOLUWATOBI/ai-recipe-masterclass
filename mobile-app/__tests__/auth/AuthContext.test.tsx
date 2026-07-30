import AsyncStorage from "@react-native-async-storage/async-storage";
import { render, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Text, TouchableOpacity } from "react-native";
import { sendPhoneOtp, verifyPhoneOtp } from "../../src/api/supabaseAuth";
import { AuthProvider, useAuth } from "../../src/auth/AuthContext";

jest.mock("../../src/api/supabaseAuth");
const mockedSendPhoneOtp = sendPhoneOtp as jest.MockedFunction<typeof sendPhoneOtp>;
const mockedVerifyPhoneOtp = verifyPhoneOtp as jest.MockedFunction<typeof verifyPhoneOtp>;

function Probe() {
  const { isHydrated, phone, isLoggedIn, sendCode, verifyCode, logOut } = useAuth();
  return (
    <>
      <Text testID="hydrated">{String(isHydrated)}</Text>
      <Text testID="phone">{phone ?? "none"}</Text>
      <Text testID="logged-in">{String(isLoggedIn)}</Text>
      <TouchableOpacity testID="send-code" onPress={() => sendCode("+4791234567")}>
        <Text>send</Text>
      </TouchableOpacity>
      <TouchableOpacity
        testID="verify-code"
        onPress={() => {
          // Swallowed here deliberately: this probe only asserts on resulting state,
          // and a failed verifyCode() is expected to reject in one of the tests below
          // -- an uncaught rejection from the onPress handler itself would otherwise
          // surface as an unhandled-rejection failure independent of what the test's
          // own assertions check.
          verifyCode("+4791234567", "123456").catch(() => {});
        }}
      >
        <Text>verify</Text>
      </TouchableOpacity>
      <TouchableOpacity testID="log-out" onPress={() => logOut()}>
        <Text>log out</Text>
      </TouchableOpacity>
    </>
  );
}

async function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    mockedSendPhoneOtp.mockReset();
    mockedVerifyPhoneOtp.mockReset();
  });

  afterEach(async () => {
    await AsyncStorage.clear();
  });

  it("starts logged out once hydrated", async () => {
    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("hydrated").props.children).toBe("true"));
    expect(screen.getByTestId("logged-in").props.children).toBe("false");
    expect(screen.getByTestId("phone").props.children).toBe("none");
  });

  it("sendCode delegates to sendPhoneOtp without changing login state", async () => {
    mockedSendPhoneOtp.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("send-code"));

    expect(mockedSendPhoneOtp).toHaveBeenCalledWith("+4791234567");
    expect(screen.getByTestId("logged-in").props.children).toBe("false");
  });

  it("verifyCode logs the user in and persists the session", async () => {
    mockedVerifyPhoneOtp.mockResolvedValueOnce({
      access_token: "abc", refresh_token: "def", expires_in: 3600, token_type: "bearer",
    });
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("verify-code"));

    await waitFor(() => expect(screen.getByTestId("logged-in").props.children).toBe("true"));
    expect(screen.getByTestId("phone").props.children).toBe("+4791234567");

    const stored = await AsyncStorage.getItem("auth_session");
    expect(JSON.parse(stored as string).phone).toBe("+4791234567");
  });

  it("verifyCode with a wrong code leaves the user logged out", async () => {
    mockedVerifyPhoneOtp.mockRejectedValueOnce(new Error("invalid code"));
    const user = userEvent.setup();
    await renderProbe();

    // verifyCode() itself doesn't swallow a failure (that's the calling screen's job,
    // see VerifyOtpScreen's own try/catch) -- this just confirms a rejected call never
    // sets a session, regardless of who's catching the rejection.
    await user.press(screen.getByTestId("verify-code"));

    expect(screen.getByTestId("logged-in").props.children).toBe("false");
  });

  it("logOut clears the session and removes it from storage", async () => {
    mockedVerifyPhoneOtp.mockResolvedValueOnce({
      access_token: "abc", refresh_token: "def", expires_in: 3600, token_type: "bearer",
    });
    const user = userEvent.setup();
    await renderProbe();
    await user.press(screen.getByTestId("verify-code"));
    await waitFor(() => expect(screen.getByTestId("logged-in").props.children).toBe("true"));

    await user.press(screen.getByTestId("log-out"));

    expect(screen.getByTestId("logged-in").props.children).toBe("false");
    await waitFor(async () => expect(await AsyncStorage.getItem("auth_session")).toBeNull());
  });

  it("loads a previously persisted session on mount", async () => {
    await AsyncStorage.setItem(
      "auth_session",
      JSON.stringify({ access_token: "abc", refresh_token: "def", expires_in: 3600, token_type: "bearer", phone: "+4799999999" })
    );

    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("logged-in").props.children).toBe("true"));
    expect(screen.getByTestId("phone").props.children).toBe("+4799999999");
  });

  it("ignores a corrupt persisted session and starts logged out", async () => {
    await AsyncStorage.setItem("auth_session", "not json");

    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("hydrated").props.children).toBe("true"));
    expect(screen.getByTestId("logged-in").props.children).toBe("false");
  });
});

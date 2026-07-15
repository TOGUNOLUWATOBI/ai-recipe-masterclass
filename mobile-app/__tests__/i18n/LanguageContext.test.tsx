import AsyncStorage from "@react-native-async-storage/async-storage";
import { render, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Text, TouchableOpacity } from "react-native";
import { useLanguage } from "../../src/i18n/LanguageContext";
import { DEFAULT_LANGUAGE, setLanguage as resetSharedLanguage } from "../../src/i18n/language";
import { renderWithProviders } from "../../test-utils/testUtils";

function Probe() {
  const { language, setLanguage, t } = useLanguage();
  return (
    <>
      <Text testID="probe-language">{language}</Text>
      <Text testID="probe-translated">{t.tabDeals}</Text>
      <TouchableOpacity testID="probe-switch-to-no" onPress={() => setLanguage("no")}>
        <Text>switch</Text>
      </TouchableOpacity>
    </>
  );
}

class CaughtErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <Text testID="caught-error">{this.state.error.message}</Text>;
    }
    return this.props.children;
  }
}

describe("LanguageContext", () => {
  afterEach(async () => {
    await AsyncStorage.clear();
    resetSharedLanguage(DEFAULT_LANGUAGE);
  });

  it("useLanguage() throws when called outside a LanguageProvider", async () => {
    // Rendering directly (not via renderWithProviders) to deliberately skip the
    // wrapper -- caught via an error boundary since React's test renderer doesn't
    // propagate a render-time throw back through render() itself in a way a plain
    // try/catch or toThrow() around the render call can catch.
    const originalConsoleError = console.error;
    console.error = jest.fn(); // suppress React's own noisy error-boundary logging
    try {
      const { getByTestId } = await render(
        <CaughtErrorBoundary>
          <Probe />
        </CaughtErrorBoundary>
      );
      expect(getByTestId("caught-error").props.children).toBe(
        "useLanguage() must be called within a LanguageProvider"
      );
    } finally {
      console.error = originalConsoleError;
    }
  });

  it("defaults to English before any persisted value loads", async () => {
    await renderWithProviders(<Probe />);

    expect(screen.getByTestId("probe-language").props.children).toBe("en");
    expect(screen.getByTestId("probe-translated").props.children).toBe("Deals");
  });

  it("setLanguage updates the translated text reactively", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<Probe />);

    await user.press(screen.getByTestId("probe-switch-to-no"));

    expect(screen.getByTestId("probe-language").props.children).toBe("no");
    expect(screen.getByTestId("probe-translated").props.children).toBe("Tilbud");
  });

  it("persists the selected language to AsyncStorage", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<Probe />);

    await user.press(screen.getByTestId("probe-switch-to-no"));

    await waitFor(async () => expect(await AsyncStorage.getItem("language")).toBe("no"));
  });

  it("loads a previously persisted language on mount", async () => {
    await AsyncStorage.setItem("language", "no");

    await renderWithProviders(<Probe />);

    await waitFor(() => expect(screen.getByTestId("probe-language").props.children).toBe("no"));
    expect(screen.getByTestId("probe-translated").props.children).toBe("Tilbud");
  });

  it("ignores a corrupt persisted value and keeps the English default", async () => {
    await AsyncStorage.setItem("language", "fr");

    await renderWithProviders(<Probe />);

    expect(screen.getByTestId("probe-language").props.children).toBe("en");
  });
});

import AsyncStorage from "@react-native-async-storage/async-storage";
import { render, screen, userEvent, waitFor } from "@testing-library/react-native";
import React from "react";
import { Text, TouchableOpacity } from "react-native";
import { ConsentProvider, useConsent } from "../../src/consent/ConsentContext";

function Probe() {
  const { isHydrated, hasAcceptedTerms, acceptTerms } = useConsent();
  return (
    <>
      <Text testID="hydrated">{String(isHydrated)}</Text>
      <Text testID="accepted">{String(hasAcceptedTerms)}</Text>
      <TouchableOpacity testID="accept" onPress={() => acceptTerms()}>
        <Text>accept</Text>
      </TouchableOpacity>
    </>
  );
}

async function renderProbe() {
  return render(
    <ConsentProvider>
      <Probe />
    </ConsentProvider>
  );
}

describe("ConsentContext", () => {
  afterEach(async () => {
    await AsyncStorage.clear();
  });

  it("starts not-accepted once hydrated, on a fresh install", async () => {
    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("hydrated").props.children).toBe("true"));
    expect(screen.getByTestId("accepted").props.children).toBe("false");
  });

  it("acceptTerms flips hasAcceptedTerms and persists it", async () => {
    const user = userEvent.setup();
    await renderProbe();

    await user.press(screen.getByTestId("accept"));

    expect(screen.getByTestId("accepted").props.children).toBe("true");
    await waitFor(async () => expect(await AsyncStorage.getItem("has_accepted_terms")).toBe("true"));
  });

  it("loads a previously accepted state on mount", async () => {
    await AsyncStorage.setItem("has_accepted_terms", "true");

    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("accepted").props.children).toBe("true"));
  });

  it("treats anything other than the literal string 'true' as not accepted", async () => {
    await AsyncStorage.setItem("has_accepted_terms", "garbage");

    await renderProbe();

    await waitFor(() => expect(screen.getByTestId("hydrated").props.children).toBe("true"));
    expect(screen.getByTestId("accepted").props.children).toBe("false");
  });
});

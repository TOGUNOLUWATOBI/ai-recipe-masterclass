import { screen, userEvent } from "@testing-library/react-native";
import React, { useState } from "react";
import { CountryCodeSelector, DEFAULT_COUNTRY, type Country } from "../../src/components/CountryCodeSelector";
import { renderWithProviders } from "../../test-utils/testUtils";

function Harness() {
  const [country, setCountry] = useState<Country>(DEFAULT_COUNTRY);
  return <CountryCodeSelector selected={country} onSelect={setCountry} />;
}

describe("CountryCodeSelector", () => {
  it("defaults to Norway", async () => {
    await renderWithProviders(<Harness />);

    expect(screen.getByTestId("country-code-selector")).toHaveTextContent(/\+47/);
  });

  it("opens a list of countries when tapped, including Norway and Sweden", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<Harness />);

    await user.press(screen.getByTestId("country-code-selector"));

    // FlatList only renders its initial render window in tests, not the full 12-item
    // list, so this only asserts on entries near the top rather than every country.
    expect(await screen.findByTestId("country-code-modal")).toBeTruthy();
    expect(screen.getByTestId("country-option-NO")).toBeTruthy();
    expect(screen.getByTestId("country-option-SE")).toBeTruthy();
  });

  it("updates the trigger and closes the list when a country is picked", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<Harness />);

    await user.press(screen.getByTestId("country-code-selector"));
    await user.press(screen.getByTestId("country-option-SE"));

    expect(screen.getByTestId("country-code-selector")).toHaveTextContent(/\+46/);
    expect(screen.queryByTestId("country-code-modal")).toBeNull();
  });
});

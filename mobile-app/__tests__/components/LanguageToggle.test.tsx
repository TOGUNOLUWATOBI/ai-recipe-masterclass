import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { Text } from "react-native";
import { LanguageToggle } from "../../src/components/LanguageToggle";
import { useLanguage } from "../../src/i18n/LanguageContext";
import { renderWithProviders } from "../../test-utils/testUtils";

function ScreenWithToggle() {
  const { t } = useLanguage();
  return (
    <>
      <Text testID="translated-heading">{t.tabDeals}</Text>
      <LanguageToggle />
    </>
  );
}

describe("LanguageToggle", () => {
  it("renders both language options", async () => {
    await renderWithProviders(<LanguageToggle />);

    expect(screen.getByTestId("language-toggle-en")).toBeTruthy();
    expect(screen.getByTestId("language-toggle-no")).toBeTruthy();
  });

  it("pressing NO switches the rest of the screen to Norwegian", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<ScreenWithToggle />);
    expect(screen.getByTestId("translated-heading").props.children).toBe("Deals");

    await user.press(screen.getByTestId("language-toggle-no"));

    expect(screen.getByTestId("translated-heading").props.children).toBe("Tilbud");
  });

  it("pressing EN after NO switches back to English", async () => {
    const user = userEvent.setup();
    await renderWithProviders(<ScreenWithToggle />);

    await user.press(screen.getByTestId("language-toggle-no"));
    expect(screen.getByTestId("translated-heading").props.children).toBe("Tilbud");
    await user.press(screen.getByTestId("language-toggle-en"));

    expect(screen.getByTestId("translated-heading").props.children).toBe("Deals");
  });
});

import { render } from "@testing-library/react-native";
import React from "react";
import { LanguageProvider } from "../src/i18n/LanguageContext";

/**
 * Every screen/component now reads translated strings via useLanguage(), which
 * throws outside a LanguageProvider -- this wraps render() the same way App.tsx
 * wraps the real component tree, so tests don't need to repeat the wrapper
 * themselves. Defaults to English (LanguageProvider's own default), matching what a
 * fresh install shows before any language is persisted.
 */
export function renderWithProviders(ui: React.ReactElement) {
  return render(<LanguageProvider>{ui}</LanguageProvider>);
}

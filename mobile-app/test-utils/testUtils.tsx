import { render } from "@testing-library/react-native";
import React from "react";
import { CartProvider } from "../src/cart/CartContext";
import { LanguageProvider } from "../src/i18n/LanguageContext";

/**
 * Every screen/component now reads translated strings via useLanguage() and cart
 * state via useCart(), both of which throw outside their provider -- this wraps
 * render() the same way App.tsx wraps the real component tree, so tests don't need
 * to repeat the wrapper themselves. Defaults to English and an empty cart, matching
 * what a fresh install shows before any language/cart data is persisted.
 */
export function renderWithProviders(ui: React.ReactElement) {
  return render(
    <LanguageProvider>
      <CartProvider>{ui}</CartProvider>
    </LanguageProvider>
  );
}

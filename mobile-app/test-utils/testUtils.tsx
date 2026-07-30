import { render } from "@testing-library/react-native";
import React from "react";
import { AuthProvider } from "../src/auth/AuthContext";
import { CartProvider } from "../src/cart/CartContext";
import { LanguageProvider } from "../src/i18n/LanguageContext";

/**
 * Every screen/component now reads translated strings via useLanguage(), cart state
 * via useCart(), and login state via useAuth(), all of which throw outside their
 * provider -- this wraps render() the same way App.tsx wraps the real component tree,
 * so tests don't need to repeat the wrapper themselves. Defaults to English, an empty
 * cart, and logged out, matching what a fresh install shows before any persisted data
 * exists.
 */
export function renderWithProviders(ui: React.ReactElement) {
  return render(
    <LanguageProvider>
      <AuthProvider>
        <CartProvider>{ui}</CartProvider>
      </AuthProvider>
    </LanguageProvider>
  );
}

import { StatusBar } from "expo-status-bar";
import React from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { CartProvider } from "./src/cart/CartContext";
import { LanguageProvider } from "./src/i18n/LanguageContext";
import { AppNavigator } from "./src/navigation/AppNavigator";

export default function App() {
  return (
    <SafeAreaProvider>
      <LanguageProvider>
        <CartProvider>
          <AppNavigator />
        </CartProvider>
      </LanguageProvider>
      <StatusBar style="auto" />
    </SafeAreaProvider>
  );
}

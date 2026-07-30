import { useFonts } from "expo-font";
import { StatusBar } from "expo-status-bar";
import React from "react";
import { ActivityIndicator, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider } from "./src/auth/AuthContext";
import { CartProvider } from "./src/cart/CartContext";
import { LanguageProvider } from "./src/i18n/LanguageContext";
import { AppNavigator } from "./src/navigation/AppNavigator";
import { FONT_ASSETS } from "./src/theme/typography";

export default function App() {
  // Gates rendering until the bundled Inter font is ready -- every screen assumes it
  // via components/AppText.tsx, so showing the real UI before the font loads would
  // flash the OS default font first. Same red spinner already used for every other
  // loading state in this app (see e.g. DealDetailScreen).
  const [fontsLoaded] = useFonts(FONT_ASSETS);

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f5f5f5" }}>
        <ActivityIndicator size="large" color="#e63946" />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <LanguageProvider>
        <AuthProvider>
          <CartProvider>
            <AppNavigator />
          </CartProvider>
        </AuthProvider>
      </LanguageProvider>
      <StatusBar style="auto" />
    </SafeAreaProvider>
  );
}

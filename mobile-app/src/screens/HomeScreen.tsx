import { Ionicons } from "@expo/vector-icons";
import type { BottomTabNavigationProp } from "@react-navigation/bottom-tabs";
import type { CompositeNavigationProp } from "@react-navigation/native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback } from "react";
import { Alert, StyleSheet, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "../auth/AuthContext";
import { useCart } from "../cart/CartContext";
import { Text } from "../components/AppText";
import { LanguageToggle } from "../components/LanguageToggle";
import { useLanguage } from "../i18n/LanguageContext";
import type { HomeStackParamList, RootTabParamList } from "../navigation/types";
import { FONT_BOLD } from "../theme/typography";

// Landing tab (front page): app name + motto, a "Dagens Deals" shortcut straight to
// the Deals tab, the same 4 destinations as the bottom tab bar surfaced as big
// buttons, and the account section (log in / log out / delete my data) -- this tab is
// purely navigational plus account state, it owns no product/discount data of its own.
const NAV_BUTTONS: {
  route: keyof RootTabParamList;
  icon: keyof typeof Ionicons.glyphMap;
  labelKey: "tabDeals" | "tabCart" | "tabAsk" | "tabMealIdeas";
}[] = [
  { route: "Tilbud", icon: "pricetags", labelKey: "tabDeals" },
  { route: "Cart", icon: "cart", labelKey: "tabCart" },
  { route: "Ask", icon: "chatbubble-ellipses", labelKey: "tabAsk" },
  { route: "MealIdeas", icon: "restaurant", labelKey: "tabMealIdeas" },
];

// Needs both levels: "Login"/"VerifyOtp" live in this screen's own HomeStackNavigator,
// while "Tilbud"/"Cart"/"Ask"/"MealIdeas" are sibling tabs one level up -- React
// Navigation resolves a navigate() call against either level automatically, but the
// type has to name both to type-check each call correctly.
type HomeScreenNavigationProp = CompositeNavigationProp<
  NativeStackNavigationProp<HomeStackParamList, "HomeMain">,
  BottomTabNavigationProp<RootTabParamList, "Home">
>;

export function HomeScreen() {
  const navigation = useNavigation<HomeScreenNavigationProp>();
  const insets = useSafeAreaInsets();
  const { t } = useLanguage();
  const { phone, isLoggedIn, logOut } = useAuth();
  const { clearCart } = useCart();

  const handleDeleteMyData = useCallback(() => {
    Alert.alert(t.deleteMyDataConfirmTitle, t.deleteMyDataConfirmMessage, [
      { text: t.cancel, style: "cancel" },
      {
        text: t.delete,
        style: "destructive",
        onPress: () => {
          clearCart();
          logOut();
        },
      },
    ]);
  }, [clearCart, logOut, t]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + 16 }]} testID="home-screen">
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.appName}>{t.appName}</Text>
          <Text style={styles.motto}>{t.appMotto}</Text>
        </View>
        <LanguageToggle />
      </View>

      <TouchableOpacity
        style={styles.dagensDealsButton}
        onPress={() => navigation.navigate("Tilbud")}
        testID="dagens-deals-button"
      >
        <Ionicons name="flame" size={22} color="#fff" />
        <Text style={styles.dagensDealsText}>{t.homeDagensDealsButton}</Text>
      </TouchableOpacity>

      <Text style={styles.navHeading}>{t.homeNavHeading}</Text>
      <View style={styles.grid}>
        {NAV_BUTTONS.map(({ route, icon, labelKey }) => (
          <TouchableOpacity
            key={route}
            style={styles.navButton}
            onPress={() => navigation.navigate(route)}
            testID={`home-nav-${route}`}
          >
            <Ionicons name={icon} size={26} color="#e63946" />
            <Text style={styles.navButtonText}>{t[labelKey]}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.navHeading}>{t.homeAccountHeading}</Text>
      {isLoggedIn ? (
        <View style={styles.accountCard}>
          <Text style={styles.accountText}>{t.homeLoggedInAs(phone ?? "")}</Text>
          <TouchableOpacity onPress={logOut} testID="logout-button">
            <Text style={styles.accountActionText}>{t.homeLogoutButton}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={handleDeleteMyData} testID="delete-my-data-button">
            <Text style={styles.deleteText}>{t.homeDeleteMyDataButton}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <TouchableOpacity style={styles.loginButton} onPress={() => navigation.navigate("Login")} testID="login-button">
          <Ionicons name="log-in-outline" size={20} color="#e63946" />
          <Text style={styles.loginButtonText}>{t.homeLoginButton}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", paddingHorizontal: 16 },
  headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 },
  appName: { fontSize: 24, fontWeight: "800", fontFamily: FONT_BOLD, color: "#1a1a1a" },
  motto: { fontSize: 14, color: "#666", fontStyle: "italic", marginTop: 2 },
  dagensDealsButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#e63946",
    borderRadius: 12,
    paddingVertical: 16,
    marginBottom: 24,
  },
  dagensDealsText: { color: "#fff", fontSize: 16, fontWeight: "700", fontFamily: FONT_BOLD },
  navHeading: {
    fontSize: 13,
    fontWeight: "700",
    fontFamily: FONT_BOLD,
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginBottom: 10,
    marginTop: 8,
  },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginBottom: 8 },
  navButton: {
    width: "47%",
    backgroundColor: "#fff",
    borderRadius: 12,
    paddingVertical: 20,
    alignItems: "center",
    gap: 8,
  },
  navButtonText: { fontSize: 14, fontWeight: "700", fontFamily: FONT_BOLD, color: "#1a1a1a" },
  loginButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e63946",
    paddingVertical: 14,
    marginBottom: 24,
  },
  loginButtonText: { color: "#e63946", fontSize: 15, fontWeight: "700", fontFamily: FONT_BOLD },
  accountCard: { backgroundColor: "#fff", borderRadius: 12, padding: 16, gap: 10, marginBottom: 24 },
  accountText: { fontSize: 14, color: "#1a1a1a" },
  accountActionText: { color: "#666", fontSize: 14, fontWeight: "600" },
  deleteText: { color: "#e63946", fontSize: 14, fontWeight: "700" },
});

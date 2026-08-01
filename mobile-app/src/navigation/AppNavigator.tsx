import { Ionicons } from "@expo/vector-icons";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { useCart } from "../cart/CartContext";
import { useConsent } from "../consent/ConsentContext";
import { useLanguage } from "../i18n/LanguageContext";
import { AskScreen } from "../screens/AskScreen";
import { CartScreen } from "../screens/CartScreen";
import { PrivacyPolicyScreen } from "../screens/PrivacyPolicyScreen";
import { SettingsScreen } from "../screens/SettingsScreen";
import { TermsAndConditionsScreen } from "../screens/TermsAndConditionsScreen";
import { TermsGateScreen } from "../screens/TermsGateScreen";
import type { RootStackParamList, RootTabParamList } from "./types";
import { MealIdeasStackNavigator } from "./MealIdeasStackNavigator";
import { TilbudStackNavigator } from "./TilbudStackNavigator";

const Tab = createBottomTabNavigator<RootTabParamList>();
const Stack = createNativeStackNavigator<RootStackParamList>();

const TAB_ICONS: Record<string, { filled: keyof typeof Ionicons.glyphMap; outline: keyof typeof Ionicons.glyphMap }> = {
  Tilbud: { filled: "home", outline: "home-outline" },
  Cart: { filled: "cart", outline: "cart-outline" },
  Ask: { filled: "chatbubble-ellipses", outline: "chatbubble-ellipses-outline" },
  MealIdeas: { filled: "restaurant", outline: "restaurant-outline" },
  Settings: { filled: "settings", outline: "settings-outline" },
};

// "Home" is the deals stack directly (Tilbud's own title is tabHome below) -- there's
// no separate dashboard screen, see SettingsScreen.tsx/TermsGateScreen.tsx for where
// the app-name header and legal/data actions live instead.
function MainTabNavigator() {
  const { t } = useLanguage();
  const { items } = useCart();
  const cartBadgeCount = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: "#e63946",
        tabBarInactiveTintColor: "#999",
        tabBarHideOnKeyboard: true,
        tabBarIcon: ({ color, size, focused }) => (
          <Ionicons name={focused ? TAB_ICONS[route.name].filled : TAB_ICONS[route.name].outline} color={color} size={size} />
        ),
      })}
    >
      <Tab.Screen name="Tilbud" component={TilbudStackNavigator} options={{ title: t.tabHome }} />
      <Tab.Screen
        name="Cart"
        component={CartScreen}
        options={{ title: t.tabCart, tabBarBadge: cartBadgeCount > 0 ? cartBadgeCount : undefined }}
      />
      <Tab.Screen name="Ask" component={AskScreen} options={{ title: t.tabAsk }} />
      <Tab.Screen name="MealIdeas" component={MealIdeasStackNavigator} options={{ title: t.tabMealIdeas }} />
      <Tab.Screen name="Settings" component={SettingsScreen} options={{ title: t.settingsHeading }} />
    </Tab.Navigator>
  );
}

export function AppNavigator() {
  const { t } = useLanguage();
  const { isHydrated, hasAcceptedTerms } = useConsent();

  // Waits for ConsentContext's own AsyncStorage read (see ConsentContext.tsx's
  // isHydrated) so a returning user who already accepted never flashes the Terms gate
  // before that's confirmed -- same reasoning as CartContext's own hydration guard.
  if (!isHydrated) {
    return null;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: "#fff" },
          headerTintColor: "#e63946",
          headerTitleStyle: { color: "#1a1a1a", fontWeight: "700" },
          headerShadowVisible: false,
          headerBackButtonDisplayMode: "minimal",
          animation: "slide_from_right",
        }}
      >
        {hasAcceptedTerms ? (
          <Stack.Screen name="MainTabs" component={MainTabNavigator} options={{ headerShown: false }} />
        ) : (
          <Stack.Screen name="TermsGate" component={TermsGateScreen} options={{ headerShown: false }} />
        )}
        <Stack.Screen name="TermsAndConditions" component={TermsAndConditionsScreen} options={{ title: t.termsTitle }} />
        <Stack.Screen name="PrivacyPolicy" component={PrivacyPolicyScreen} options={{ title: t.privacyPolicyTitle }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

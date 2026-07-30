import { Ionicons } from "@expo/vector-icons";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { NavigationContainer } from "@react-navigation/native";
import React from "react";
import { useCart } from "../cart/CartContext";
import { useLanguage } from "../i18n/LanguageContext";
import type { RootTabParamList } from "./types";
import { AskScreen } from "../screens/AskScreen";
import { CartScreen } from "../screens/CartScreen";
import { HomeStackNavigator } from "./HomeStackNavigator";
import { MealIdeasStackNavigator } from "./MealIdeasStackNavigator";
import { TilbudStackNavigator } from "./TilbudStackNavigator";

const Tab = createBottomTabNavigator<RootTabParamList>();

const TAB_ICONS: Record<string, { filled: keyof typeof Ionicons.glyphMap; outline: keyof typeof Ionicons.glyphMap }> = {
  Home: { filled: "home", outline: "home-outline" },
  Tilbud: { filled: "pricetags", outline: "pricetags-outline" },
  Cart: { filled: "cart", outline: "cart-outline" },
  Ask: { filled: "chatbubble-ellipses", outline: "chatbubble-ellipses-outline" },
  MealIdeas: { filled: "restaurant", outline: "restaurant-outline" },
};

export function AppNavigator() {
  const { t } = useLanguage();
  const { items } = useCart();
  const cartBadgeCount = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <NavigationContainer>
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
        <Tab.Screen name="Home" component={HomeStackNavigator} options={{ title: t.tabHome }} />
        <Tab.Screen name="Tilbud" component={TilbudStackNavigator} options={{ title: t.tabDeals }} />
        <Tab.Screen
          name="Cart"
          component={CartScreen}
          options={{ title: t.tabCart, tabBarBadge: cartBadgeCount > 0 ? cartBadgeCount : undefined }}
        />
        <Tab.Screen name="Ask" component={AskScreen} options={{ title: t.tabAsk }} />
        <Tab.Screen name="MealIdeas" component={MealIdeasStackNavigator} options={{ title: t.tabMealIdeas }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

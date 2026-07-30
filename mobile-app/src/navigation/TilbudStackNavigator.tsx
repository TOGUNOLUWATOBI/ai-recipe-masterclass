import { Ionicons } from "@expo/vector-icons";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { TouchableOpacity } from "react-native";
import { useLanguage } from "../i18n/LanguageContext";
import { DealDetailScreen } from "../screens/DealDetailScreen";
import { StoreItemsScreen } from "../screens/StoreItemsScreen";
import { StoresScreen } from "../screens/StoresScreen";
import type { TilbudStackParamList } from "./types";

const Stack = createNativeStackNavigator<TilbudStackParamList>();

export function TilbudStackNavigator() {
  const { t } = useLanguage();

  return (
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
      <Stack.Screen name="StoresList" component={StoresScreen} options={{ headerShown: false }} />
      <Stack.Screen
        name="StoreItems"
        component={StoreItemsScreen}
        options={({ route }) => ({ title: route.params.store.storeName })}
      />
      <Stack.Screen
        name="DealDetail"
        component={DealDetailScreen}
        options={({ navigation }) => ({
          title: t.dealDetailTitle,
          // An explicit close affordance alongside the standard back arrow -- some
          // users don't read a chevron as "close this panel", an X reads unambiguously
          // either way. Same goBack() the back arrow already triggers, just a second
          // way to reach it.
          headerRight: () => (
            <TouchableOpacity onPress={() => navigation.goBack()} testID="deal-detail-close-button">
              <Ionicons name="close" size={26} color="#1a1a1a" />
            </TouchableOpacity>
          ),
        })}
      />
    </Stack.Navigator>
  );
}

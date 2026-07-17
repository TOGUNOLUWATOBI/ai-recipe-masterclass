import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { useLanguage } from "../i18n/LanguageContext";
import { MealIdeaResultsScreen } from "../screens/MealIdeaResultsScreen";
import { MealIdeaStoreSelectionScreen } from "../screens/MealIdeaStoreSelectionScreen";
import { MealIdeasScreen } from "../screens/MealIdeasScreen";
import type { MealIdeasStackParamList } from "./types";

const Stack = createNativeStackNavigator<MealIdeasStackParamList>();

export function MealIdeasStackNavigator() {
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
      <Stack.Screen name="MealIdeasHome" component={MealIdeasScreen} options={{ headerShown: false }} />
      <Stack.Screen
        name="MealIdeasStoreSelection"
        component={MealIdeaStoreSelectionScreen}
        options={{ title: t.mealIdeasChooseStoreHeading }}
      />
      <Stack.Screen
        name="MealIdeasResults"
        component={MealIdeaResultsScreen}
        options={{ title: t.mealIdeasEntryHeading }}
      />
    </Stack.Navigator>
  );
}

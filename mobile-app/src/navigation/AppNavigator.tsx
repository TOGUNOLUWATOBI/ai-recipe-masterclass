import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { NavigationContainer } from "@react-navigation/native";
import React from "react";
import { AskScreen } from "../screens/AskScreen";
import { IngredientsScreen } from "../screens/IngredientsScreen";
import { TilbudStackNavigator } from "./TilbudStackNavigator";

const Tab = createBottomTabNavigator();

export function AppNavigator() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{ headerShown: false }}>
        <Tab.Screen name="Tilbud" component={TilbudStackNavigator} options={{ title: "Deals" }} />
        <Tab.Screen name="Ask" component={AskScreen} />
        <Tab.Screen name="Ingredients" component={IngredientsScreen} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { DealDetailScreen } from "../screens/DealDetailScreen";
import { StoreItemsScreen } from "../screens/StoreItemsScreen";
import { StoresScreen } from "../screens/StoresScreen";
import type { TilbudStackParamList } from "./types";

const Stack = createNativeStackNavigator<TilbudStackParamList>();

export function TilbudStackNavigator() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="StoresList" component={StoresScreen} options={{ headerShown: false }} />
      <Stack.Screen
        name="StoreItems"
        component={StoreItemsScreen}
        options={({ route }) => ({ title: route.params.store.storeName })}
      />
      <Stack.Screen name="DealDetail" component={DealDetailScreen} options={{ title: "Oppskrift" }} />
    </Stack.Navigator>
  );
}

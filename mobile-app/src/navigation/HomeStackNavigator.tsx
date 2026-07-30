import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { useLanguage } from "../i18n/LanguageContext";
import { HomeScreen } from "../screens/HomeScreen";
import { LoginScreen } from "../screens/LoginScreen";
import { PrivacyPolicyScreen } from "../screens/PrivacyPolicyScreen";
import { VerifyOtpScreen } from "../screens/VerifyOtpScreen";
import type { HomeStackParamList } from "./types";

const Stack = createNativeStackNavigator<HomeStackParamList>();

export function HomeStackNavigator() {
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
      <Stack.Screen name="HomeMain" component={HomeScreen} options={{ headerShown: false }} />
      <Stack.Screen name="Login" component={LoginScreen} options={{ title: t.authLoginHeading }} />
      <Stack.Screen name="VerifyOtp" component={VerifyOtpScreen} options={{ title: t.authVerifyHeading }} />
      <Stack.Screen name="PrivacyPolicy" component={PrivacyPolicyScreen} options={{ title: t.privacyPolicyTitle }} />
    </Stack.Navigator>
  );
}

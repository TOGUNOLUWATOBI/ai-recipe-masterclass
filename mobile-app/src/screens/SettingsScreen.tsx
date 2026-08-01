import type { BottomTabNavigationProp } from "@react-navigation/bottom-tabs";
import type { CompositeNavigationProp } from "@react-navigation/native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback } from "react";
import { Alert, StyleSheet, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCart } from "../cart/CartContext";
import { Text } from "../components/AppText";
import { LanguageToggle } from "../components/LanguageToggle";
import { useLanguage } from "../i18n/LanguageContext";
import type { RootStackParamList, RootTabParamList } from "../navigation/types";
import { FONT_BOLD } from "../theme/typography";

// Data/legal actions -- reachable at any time via the tab bar. TermsAndConditions/
// PrivacyPolicy live in the root stack one level up (see navigation/types.ts), not
// nested under this tab, so both the pre-app Terms gate and this tab reach the same
// screens.
type SettingsScreenNavigationProp = CompositeNavigationProp<
  BottomTabNavigationProp<RootTabParamList, "Settings">,
  NativeStackNavigationProp<RootStackParamList>
>;

export function SettingsScreen() {
  const navigation = useNavigation<SettingsScreenNavigationProp>();
  const insets = useSafeAreaInsets();
  const { t } = useLanguage();
  const { clearCart } = useCart();

  const handleDeleteMyData = useCallback(() => {
    Alert.alert(t.deleteMyDataConfirmTitle, t.deleteMyDataConfirmMessage, [
      { text: t.cancel, style: "cancel" },
      { text: t.delete, style: "destructive", onPress: clearCart },
    ]);
  }, [clearCart, t]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + 16 }]} testID="settings-screen">
      <View style={styles.headerRow}>
        <Text style={styles.heading}>{t.settingsHeading}</Text>
        <LanguageToggle />
      </View>

      <TouchableOpacity style={styles.actionRow} onPress={handleDeleteMyData} testID="delete-my-data-button">
        <Text style={styles.deleteText}>{t.settingsDeleteMyDataButton}</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate("TermsAndConditions")}
        testID="settings-terms-link"
      >
        <Text style={styles.linkText}>{t.termsTitle}</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate("PrivacyPolicy")}
        testID="settings-privacy-policy-link"
      >
        <Text style={styles.linkText}>{t.privacyPolicyTitle}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", paddingHorizontal: 16 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 20 },
  heading: { fontSize: 26, fontWeight: "800", fontFamily: FONT_BOLD, color: "#1a1a1a" },
  actionRow: { backgroundColor: "#fff", borderRadius: 12, padding: 16, marginBottom: 12 },
  linkText: { fontSize: 15, color: "#1a1a1a", fontWeight: "600" },
  deleteText: { fontSize: 15, color: "#e63946", fontWeight: "700" },
});

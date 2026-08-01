import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React from "react";
import { Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Text } from "../components/AppText";
import { useConsent } from "../consent/ConsentContext";
import { useLanguage } from "../i18n/LanguageContext";
import type { RootStackParamList } from "../navigation/types";
import { FONT_BOLD } from "../theme/typography";

// Shown once on first launch (and again on any launch where acceptance wasn't
// persisted yet, see ConsentContext.tsx) -- reading the full Terms/Privacy Policy is
// optional but a tap away before agreeing; accepting is what actually unlocks the app,
// persisted so this screen never reappears once accepted.
export function TermsGateScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "TermsGate">>();
  const insets = useSafeAreaInsets();
  const { t } = useLanguage();
  const { acceptTerms } = useConsent();

  return (
    <View style={[styles.container, { paddingTop: insets.top + 40 }]} testID="terms-gate-screen">
      <View style={styles.hero}>
        <Image source={require("../../assets/icon.png")} style={styles.logo} resizeMode="contain" />
        <Text style={styles.appName}>{t.appName}</Text>
        <Text style={styles.motto}>{t.appMotto}</Text>
      </View>

      <View style={styles.actions}>
        <Text style={styles.agreementText}>{t.termsGateIntro}</Text>

        <View style={styles.linksRow}>
          <TouchableOpacity onPress={() => navigation.navigate("TermsAndConditions")} testID="terms-gate-terms-link">
            <Text style={styles.link}>{t.termsTitle}</Text>
          </TouchableOpacity>
          <Text style={styles.linksSeparator}>·</Text>
          <TouchableOpacity onPress={() => navigation.navigate("PrivacyPolicy")} testID="terms-gate-privacy-link">
            <Text style={styles.link}>{t.privacyPolicyTitle}</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={styles.acceptButton} onPress={acceptTerms} testID="terms-gate-accept-button">
          <Text style={styles.acceptButtonText}>{t.termsGateAcceptButton}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", paddingHorizontal: 24, justifyContent: "space-between" },
  hero: { alignItems: "center", marginTop: 40 },
  logo: { width: 96, height: 96, borderRadius: 20, marginBottom: 20 },
  appName: { fontSize: 30, fontWeight: "800", fontFamily: FONT_BOLD, color: "#1a1a1a" },
  motto: { fontSize: 15, color: "#666", fontStyle: "italic", marginTop: 6, textAlign: "center" },
  actions: { gap: 14, marginBottom: 24 },
  agreementText: { fontSize: 13, color: "#666", textAlign: "center", lineHeight: 19 },
  linksRow: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8 },
  link: { color: "#e63946", fontSize: 13, fontWeight: "700", textDecorationLine: "underline" },
  linksSeparator: { color: "#ccc", fontSize: 13 },
  acceptButton: { backgroundColor: "#e63946", borderRadius: 12, paddingVertical: 16, alignItems: "center" },
  acceptButtonText: { color: "#fff", fontSize: 16, fontWeight: "700", fontFamily: FONT_BOLD },
});

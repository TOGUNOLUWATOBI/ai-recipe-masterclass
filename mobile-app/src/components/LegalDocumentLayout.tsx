import React from "react";
import { Image, ScrollView, StyleSheet, View } from "react-native";
import { Text } from "./AppText";
import { FONT_BOLD } from "../theme/typography";

interface Section {
  heading: string;
  body: string;
}

interface LegalDocumentLayoutProps {
  title: string;
  lastUpdated: string;
  sections: Section[];
  testID: string;
}

// Shared presentation for both PrivacyPolicyScreen and TermsAndConditionsScreen --
// same header treatment (logo, title, last-updated line) and section rhythm so the
// two legal pages read as one consistent, deliberately-designed pair rather than two
// differently-thrown-together text dumps.
export function LegalDocumentLayout({ title, lastUpdated, sections, testID }: LegalDocumentLayoutProps) {
  return (
    <ScrollView contentContainerStyle={styles.container} testID={testID}>
      <View style={styles.header}>
        <Image source={require("../../assets/icon.png")} style={styles.logo} resizeMode="contain" />
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.lastUpdated}>{lastUpdated}</Text>
      </View>
      <View style={styles.divider} />

      {sections.map((section) => (
        <View key={section.heading} style={styles.section}>
          <Text style={styles.heading}>{section.heading}</Text>
          <Text style={styles.body}>{section.body}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, paddingBottom: 40, backgroundColor: "#f5f5f5" },
  header: { alignItems: "center", marginBottom: 20 },
  logo: { width: 56, height: 56, borderRadius: 14, marginBottom: 12 },
  title: { fontSize: 22, fontWeight: "800", fontFamily: FONT_BOLD, color: "#1a1a1a", textAlign: "center" },
  lastUpdated: { fontSize: 12, color: "#999", marginTop: 4 },
  divider: { height: 1, backgroundColor: "#e5e5e5", marginBottom: 8 },
  section: { marginTop: 18 },
  heading: { fontSize: 15, fontWeight: "700", fontFamily: FONT_BOLD, color: "#1a1a1a", marginBottom: 6 },
  body: { fontSize: 14, color: "#333", lineHeight: 21 },
});

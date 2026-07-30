import React from "react";
import { StyleSheet, TouchableOpacity, View } from "react-native";
import { Text } from "./AppText";
import { useLanguage } from "../i18n/LanguageContext";
import type { Language } from "../i18n/language";

const OPTIONS: { value: Language; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "no", label: "NO" },
];

export function LanguageToggle() {
  const { language, setLanguage } = useLanguage();

  return (
    <View style={styles.row} testID="language-toggle">
      {OPTIONS.map((option) => (
        <TouchableOpacity
          key={option.value}
          style={[styles.pill, language === option.value && styles.pillActive]}
          onPress={() => setLanguage(option.value)}
          testID={`language-toggle-${option.value}`}
        >
          <Text style={[styles.text, language === option.value && styles.textActive]}>{option.label}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    backgroundColor: "#eee",
    borderRadius: 8,
    padding: 2,
  },
  pill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6 },
  pillActive: { backgroundColor: "#fff", boxShadow: "0px 1px 2px rgba(0, 0, 0, 0.1)" },
  text: { fontSize: 12, fontWeight: "700", color: "#888" },
  textActive: { color: "#1a1a1a" },
});

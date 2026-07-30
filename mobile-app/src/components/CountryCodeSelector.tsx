import React, { useState } from "react";
import { FlatList, Modal, StyleSheet, TouchableOpacity, View } from "react-native";
import { useLanguage } from "../i18n/LanguageContext";
import { FONT_BOLD } from "../theme/typography";
import { Text } from "./AppText";

export interface Country {
  name: string;
  dialCode: string;
  flag: string;
  iso2: string;
}

// A curated, not-exhaustive list -- Norway first/default since the app is Norway-first
// today; the friend's own spec asks for this "to support future international users",
// not full worldwide coverage from day one. Add more entries here as real users need
// them, no other code needs to change.
export const COUNTRIES: Country[] = [
  { name: "Norway", dialCode: "+47", flag: "🇳🇴", iso2: "NO" },
  { name: "Sweden", dialCode: "+46", flag: "🇸🇪", iso2: "SE" },
  { name: "Denmark", dialCode: "+45", flag: "🇩🇰", iso2: "DK" },
  { name: "Finland", dialCode: "+358", flag: "🇫🇮", iso2: "FI" },
  { name: "Iceland", dialCode: "+354", flag: "🇮🇸", iso2: "IS" },
  { name: "United Kingdom", dialCode: "+44", flag: "🇬🇧", iso2: "GB" },
  { name: "Germany", dialCode: "+49", flag: "🇩🇪", iso2: "DE" },
  { name: "Poland", dialCode: "+48", flag: "🇵🇱", iso2: "PL" },
  { name: "Netherlands", dialCode: "+31", flag: "🇳🇱", iso2: "NL" },
  { name: "France", dialCode: "+33", flag: "🇫🇷", iso2: "FR" },
  { name: "Spain", dialCode: "+34", flag: "🇪🇸", iso2: "ES" },
  { name: "United States", dialCode: "+1", flag: "🇺🇸", iso2: "US" },
];

export const DEFAULT_COUNTRY = COUNTRIES[0];

interface CountryCodeSelectorProps {
  selected: Country;
  onSelect: (country: Country) => void;
}

export function CountryCodeSelector({ selected, onSelect }: CountryCodeSelectorProps) {
  const [open, setOpen] = useState(false);
  const { t } = useLanguage();

  return (
    <>
      <TouchableOpacity style={styles.trigger} onPress={() => setOpen(true)} testID="country-code-selector">
        <Text style={styles.triggerText}>
          {selected.flag} {selected.dialCode}
        </Text>
      </TouchableOpacity>

      <Modal visible={open} animationType="slide" transparent onRequestClose={() => setOpen(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setOpen(false)}>
          <View style={styles.modalSheet} testID="country-code-modal">
            <Text style={styles.modalTitle}>{t.countryCodeSelectorLabel}</Text>
            <FlatList
              data={COUNTRIES}
              keyExtractor={(country) => country.iso2}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.countryRow}
                  onPress={() => {
                    onSelect(item);
                    setOpen(false);
                  }}
                  testID={`country-option-${item.iso2}`}
                >
                  <Text style={styles.countryRowText}>
                    {item.flag} {item.name} ({item.dialCode})
                  </Text>
                </TouchableOpacity>
              )}
            />
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  trigger: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#ddd",
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  triggerText: { fontSize: 15, color: "#1a1a1a" },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalSheet: { backgroundColor: "#fff", borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 16, maxHeight: "70%" },
  modalTitle: { fontSize: 16, fontWeight: "700", fontFamily: FONT_BOLD, color: "#1a1a1a", marginBottom: 12 },
  countryRow: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: "#f0f0f0" },
  countryRowText: { fontSize: 15, color: "#1a1a1a" },
});

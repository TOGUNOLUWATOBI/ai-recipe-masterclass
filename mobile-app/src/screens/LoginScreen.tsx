import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { ActivityIndicator, StyleSheet, TouchableOpacity, View } from "react-native";
import { useAuth } from "../auth/AuthContext";
import { Text } from "../components/AppText";
import { TextInput } from "../components/AppTextInput";
import { CountryCodeSelector, DEFAULT_COUNTRY, type Country } from "../components/CountryCodeSelector";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import type { HomeStackParamList } from "../navigation/types";
import { userMessageForError } from "../api/errors";
import { FONT_BOLD } from "../theme/typography";

// GDPR (Task: consent checkbox on signup): the phone number is only ever sent once
// this box is checked -- see handleSendCode below, which refuses to call sendCode()
// at all otherwise, not just hide/disable the button after the fact.
function ConsentCheckbox({ checked, onToggle }: { checked: boolean; onToggle: () => void }) {
  const navigation = useNavigation<NativeStackNavigationProp<HomeStackParamList, "Login">>();
  const { t } = useLanguage();

  return (
    <View style={styles.consentRow}>
      <TouchableOpacity onPress={onToggle} testID="consent-checkbox" style={styles.checkbox}>
        <Ionicons name={checked ? "checkbox" : "square-outline"} size={22} color={checked ? "#e63946" : "#999"} />
      </TouchableOpacity>
      <Text style={styles.consentText}>
        {t.authConsentPrefix}{" "}
        <Text style={styles.consentLink} onPress={() => navigation.navigate("PrivacyPolicy")}>
          {t.authPrivacyPolicyLinkText}
        </Text>
      </Text>
    </View>
  );
}

export function LoginScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<HomeStackParamList, "Login">>();
  const { t } = useLanguage();
  const { sendCode } = useAuth();

  const [country, setCountry] = useState<Country>(DEFAULT_COUNTRY);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [consented, setConsented] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSendCode() {
    setErrorMessage(null);
    if (!consented) {
      setErrorMessage(t.authErrorMustAgreeToPrivacyPolicy);
      return;
    }
    const digits = phoneNumber.replace(/\D/g, "");
    if (digits.length < 5) {
      setErrorMessage(t.authErrorInvalidPhone);
      return;
    }
    const fullPhone = `${country.dialCode}${digits}`;
    setLoading(true);
    try {
      await sendCode(fullPhone);
      navigation.navigate("VerifyOtp", { phone: fullPhone });
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container} testID="login-screen">
      <Text style={styles.heading}>{t.authLoginHeading}</Text>

      <Text style={styles.label}>{t.authPhoneLabel}</Text>
      <View style={styles.phoneRow}>
        <CountryCodeSelector selected={country} onSelect={setCountry} />
        <TextInput
          style={styles.phoneInput}
          value={phoneNumber}
          onChangeText={setPhoneNumber}
          placeholder={t.authPhonePlaceholder}
          keyboardType="phone-pad"
          testID="phone-input"
        />
      </View>

      <ConsentCheckbox checked={consented} onToggle={() => setConsented((prev) => !prev)} />

      {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

      <TouchableOpacity
        style={[styles.sendButton, loading && styles.sendButtonDisabled]}
        onPress={handleSendCode}
        disabled={loading}
        testID="send-code-button"
      >
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.sendButtonText}>{t.authSendCodeButton}</Text>}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 16 },
  heading: { fontSize: 24, fontWeight: "800", fontFamily: FONT_BOLD, color: "#1a1a1a", marginBottom: 20 },
  label: { fontSize: 13, fontWeight: "700", fontFamily: FONT_BOLD, color: "#666", marginBottom: 6 },
  phoneRow: { flexDirection: "row", gap: 8, marginBottom: 16 },
  phoneInput: {
    flex: 1,
    backgroundColor: "#fff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#ddd",
    paddingHorizontal: 12,
    fontSize: 15,
  },
  consentRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginBottom: 20 },
  checkbox: { paddingTop: 1 },
  consentText: { flex: 1, fontSize: 13, color: "#333", lineHeight: 18 },
  consentLink: { color: "#e63946", fontWeight: "700", textDecorationLine: "underline" },
  sendButton: { backgroundColor: "#e63946", borderRadius: 10, paddingVertical: 14, alignItems: "center" },
  sendButtonDisabled: { opacity: 0.6 },
  sendButtonText: { color: "#fff", fontSize: 16, fontWeight: "700", fontFamily: FONT_BOLD },
});

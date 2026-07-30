import type { RouteProp } from "@react-navigation/native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { ActivityIndicator, StyleSheet, TouchableOpacity, View } from "react-native";
import { userMessageForError } from "../api/errors";
import { useAuth } from "../auth/AuthContext";
import { Text } from "../components/AppText";
import { TextInput } from "../components/AppTextInput";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import type { HomeStackParamList } from "../navigation/types";
import { FONT_BOLD } from "../theme/typography";

export function VerifyOtpScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<HomeStackParamList, "VerifyOtp">>();
  const route = useRoute<RouteProp<HomeStackParamList, "VerifyOtp">>();
  const { phone } = route.params;
  const { t } = useLanguage();
  const { verifyCode, sendCode } = useAuth();

  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleVerify() {
    setErrorMessage(null);
    if (code.trim().length !== 6) {
      setErrorMessage(t.authErrorInvalidCode);
      return;
    }
    setLoading(true);
    try {
      await verifyCode(phone, code.trim());
      // Success -- back out of the login flow entirely (Login/VerifyOtp are no longer
      // relevant once logged in), landing wherever HomeScreen itself renders next.
      navigation.popToTop();
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setErrorMessage(null);
    setResending(true);
    try {
      await sendCode(phone);
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setResending(false);
    }
  }

  return (
    <View style={styles.container} testID="verify-otp-screen">
      <Text style={styles.heading}>{t.authVerifyHeading}</Text>
      <Text style={styles.subtitle}>{t.authVerifySubtitle(phone)}</Text>

      <Text style={styles.label}>{t.authOtpLabel}</Text>
      <TextInput
        style={styles.otpInput}
        value={code}
        onChangeText={setCode}
        placeholder={t.authOtpPlaceholder}
        keyboardType="number-pad"
        maxLength={6}
        testID="otp-input"
      />

      {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

      <TouchableOpacity
        style={[styles.verifyButton, loading && styles.buttonDisabled]}
        onPress={handleVerify}
        disabled={loading}
        testID="verify-code-button"
      >
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.verifyButtonText}>{t.authVerifyButton}</Text>}
      </TouchableOpacity>

      <TouchableOpacity onPress={handleResend} disabled={resending} testID="resend-code-button">
        <Text style={styles.resendText}>{t.authResendCodeButton}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 16 },
  heading: { fontSize: 24, fontWeight: "800", fontFamily: FONT_BOLD, color: "#1a1a1a", marginBottom: 6 },
  subtitle: { fontSize: 14, color: "#666", marginBottom: 20 },
  label: { fontSize: 13, fontWeight: "700", fontFamily: FONT_BOLD, color: "#666", marginBottom: 6 },
  otpInput: {
    backgroundColor: "#fff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#ddd",
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 20,
    letterSpacing: 4,
    marginBottom: 20,
  },
  verifyButton: { backgroundColor: "#e63946", borderRadius: 10, paddingVertical: 14, alignItems: "center", marginBottom: 16 },
  buttonDisabled: { opacity: 0.6 },
  verifyButtonText: { color: "#fff", fontSize: 16, fontWeight: "700", fontFamily: FONT_BOLD },
  resendText: { color: "#e63946", fontSize: 14, fontWeight: "600", textAlign: "center" },
});

import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { askQuestion } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { LanguageToggle } from "../components/LanguageToggle";
import { RecipeCard } from "../components/RecipeCard";
import { useLanguage } from "../i18n/LanguageContext";
import type { QueryResponse } from "../types/api";
import { MAX_QUESTION_LENGTH } from "../api/validation";

export function AskScreen() {
  const insets = useSafeAreaInsets();
  const { language, t } = useLanguage();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (loading) return; // guard against double-submit from rapid taps
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    try {
      const response = await askQuestion(question, language);
      if (response.error) {
        setErrorMessage(response.error);
      } else {
        setResult(response);
      }
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setLoading(false);
    }
  }, [question, loading, language]);

  const groundedTitles = result?.grounded
    .map((r) => r.payload.title)
    .filter((title): title is string => Boolean(title));

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={[styles.container, { paddingTop: insets.top + 16 }]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.headerRow}>
          <Text style={styles.heading}>{t.askHeading}</Text>
          <LanguageToggle />
        </View>
        <TextInput
          style={styles.input}
          placeholder={t.askPlaceholder}
          value={question}
          onChangeText={setQuestion}
          maxLength={MAX_QUESTION_LENGTH}
          editable={!loading}
          returnKeyType="send"
          onSubmitEditing={handleSubmit}
          testID="ask-input"
        />
        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={loading}
          testID="ask-submit"
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{t.askButton}</Text>}
        </TouchableOpacity>

        {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

        {result && !errorMessage ? (
          <>
            {groundedTitles && groundedTitles.length > 0 ? (
              <Text style={styles.groundedNote}>{t.askBasedOn(groundedTitles.join(", "))}</Text>
            ) : (
              <Text style={styles.groundedNote}>{t.askNoExactMatch}</Text>
            )}
            {result.answer ? <RecipeCard text={result.answer} /> : null}
          </>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 16, backgroundColor: "#f5f5f5", flexGrow: 1 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  heading: { fontSize: 22, fontWeight: "700" },
  input: {
    backgroundColor: "#fff",
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#ddd",
  },
  button: {
    backgroundColor: "#c0392b",
    borderRadius: 8,
    padding: 14,
    alignItems: "center",
    marginTop: 12,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: "#fff", fontWeight: "600", fontSize: 16 },
  groundedNote: { marginTop: 16, fontSize: 13, color: "#666", fontStyle: "italic" },
});

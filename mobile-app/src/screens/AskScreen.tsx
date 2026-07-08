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
import { askQuestion } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { RecipeCard } from "../components/RecipeCard";
import type { QueryResponse } from "../types/api";
import { MAX_QUESTION_LENGTH } from "../api/validation";

export function AskScreen() {
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
      const response = await askQuestion(question);
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
  }, [question, loading]);

  const groundedTitles = result?.grounded
    .map((r) => r.payload.title)
    .filter((title): title is string => Boolean(title));

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.heading}>Ask for a recipe</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g. norwegian ribbe, jollof rice, biryani..."
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
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Ask</Text>}
        </TouchableOpacity>

        {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

        {result && !errorMessage ? (
          <>
            {groundedTitles && groundedTitles.length > 0 ? (
              <Text style={styles.groundedNote}>Based on: {groundedTitles.join(", ")}</Text>
            ) : (
              <Text style={styles.groundedNote}>No exact match found — best-effort answer below.</Text>
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
  heading: { fontSize: 22, fontWeight: "700", marginBottom: 12 },
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

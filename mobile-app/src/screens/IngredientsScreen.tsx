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
import { getRecipesFromIngredients } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { RecipeCard } from "../components/RecipeCard";
import type { IngredientsResponse } from "../types/api";

export function IngredientsScreen() {
  const [ingredientsText, setIngredientsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngredientsResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    try {
      const ingredients = ingredientsText.split(",");
      const response = await getRecipesFromIngredients(ingredients, 10);
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
  }, [ingredientsText, loading]);

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.heading}>What can I cook?</Text>
        <Text style={styles.subheading}>Enter ingredients, separated by commas</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g. chicken, tomatoes, onions, rice"
          value={ingredientsText}
          onChangeText={setIngredientsText}
          editable={!loading}
          returnKeyType="send"
          onSubmitEditing={handleSubmit}
          testID="ingredients-input"
        />
        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={loading}
          testID="ingredients-submit"
        >
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Find recipes</Text>}
        </TouchableOpacity>

        {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

        {result && !errorMessage ? (
          <View>
            <Text style={styles.sourceNote}>
              {result.source === "corpus"
                ? `Found ${result.count} matching recipe${result.count === 1 ? "" : "s"}`
                : `No exact match — ${result.count} generated suggestion${result.count === 1 ? "" : "s"}`}
            </Text>
            {result.recipes.map((recipe, index) => (
              <RecipeCard key={index} title={recipe.title} text={recipe.text} />
            ))}
          </View>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 16, backgroundColor: "#f5f5f5", flexGrow: 1 },
  heading: { fontSize: 22, fontWeight: "700", marginBottom: 4 },
  subheading: { fontSize: 13, color: "#666", marginBottom: 12 },
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
  sourceNote: { marginTop: 16, marginBottom: 4, fontSize: 13, color: "#666", fontStyle: "italic" },
});

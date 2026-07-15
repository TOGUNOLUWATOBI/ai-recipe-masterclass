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
import { getRecipesFromIngredients } from "../api/client";
import { userMessageForError } from "../api/errors";
import { MAX_INGREDIENT_COUNT } from "../api/validation";
import { ErrorBanner } from "../components/ErrorBanner";
import { LanguageToggle } from "../components/LanguageToggle";
import { RecipeCard } from "../components/RecipeCard";
import { useLanguage } from "../i18n/LanguageContext";
import type { IngredientsResponse } from "../types/api";

export function IngredientsScreen() {
  const insets = useSafeAreaInsets();
  const { t } = useLanguage();
  const [ingredientsText, setIngredientsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngredientsResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [searchIngredients, setSearchIngredients] = useState<string[] | null>(null);
  const [showMoreLoading, setShowMoreLoading] = useState(false);
  const [canShowMore, setCanShowMore] = useState(false);
  const [showMoreErrorMessage, setShowMoreErrorMessage] = useState<string | null>(null);

  // The first search only asks for 1 recipe: the backend's fallback-generation path is
  // hard-capped at 3 sequential LLM calls no matter what max_results is requested, so
  // requesting 1 up front turns a ~97s worst case into ~32s. The full-screen loading
  // state on the "Find recipes" button is unchanged and only covers this first request.
  const handleSubmit = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    setCanShowMore(false);
    setShowMoreErrorMessage(null);
    const ingredients = ingredientsText.split(",");
    setSearchIngredients(ingredients);
    try {
      const response = await getRecipesFromIngredients(ingredients, 1);
      if (response.error) {
        setErrorMessage(response.error);
      } else {
        setResult(response);
        setCanShowMore(response.recipes.length > 0 && response.recipes.length < MAX_INGREDIENT_COUNT);
      }
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setLoading(false);
    }
  }, [ingredientsText, loading]);

  // "Show more" re-requests the same ingredients with a larger max_results, one more than
  // what's currently shown. It never disturbs the already-rendered cards or the "Find
  // recipes" button/spinner — only the show-more button itself reflects the in-flight
  // request. The button hides itself once a request stops returning more recipes than
  // before, which generically covers both real backend caps (the generated-fallback path
  // hard-stops at 3 total; the corpus path stops whenever no further matches clear the
  // relevance threshold) without hardcoding either number here.
  const handleShowMore = useCallback(() => {
    if (!result || !searchIngredients || showMoreLoading) return;
    const previousCount = result.recipes.length;
    const nextMax = Math.min(previousCount + 1, MAX_INGREDIENT_COUNT);
    setShowMoreLoading(true);
    setShowMoreErrorMessage(null);
    getRecipesFromIngredients(searchIngredients, nextMax)
      .then((response) => {
        if (response.error) {
          setShowMoreErrorMessage(response.error);
          return;
        }
        setResult(response);
        setCanShowMore(response.recipes.length > previousCount && nextMax < MAX_INGREDIENT_COUNT);
      })
      .catch((err) => {
        setShowMoreErrorMessage(userMessageForError(err));
      })
      .finally(() => {
        setShowMoreLoading(false);
      });
  }, [result, searchIngredients, showMoreLoading]);

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView
        contentContainerStyle={[styles.container, { paddingTop: insets.top + 16 }]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.headerRow}>
          <Text style={styles.heading}>{t.ingredientsHeading}</Text>
          <LanguageToggle />
        </View>
        <Text style={styles.subheading}>{t.ingredientsSubheading}</Text>
        <TextInput
          style={styles.input}
          placeholder={t.ingredientsPlaceholder}
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
          {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{t.ingredientsButton}</Text>}
        </TouchableOpacity>

        {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

        {result && !errorMessage ? (
          <View>
            <Text style={styles.sourceNote}>
              {result.source === "corpus"
                ? t.ingredientsFoundCorpus(result.count)
                : t.ingredientsFoundGenerated(result.count)}
            </Text>
            {result.recipes.map((recipe, index) => (
              <RecipeCard key={index} title={recipe.title} text={recipe.text} />
            ))}
            {canShowMore ? (
              <TouchableOpacity
                style={[styles.showMoreButton, showMoreLoading && styles.showMoreButtonDisabled]}
                onPress={handleShowMore}
                disabled={showMoreLoading}
                testID="show-more-button"
              >
                {showMoreLoading ? (
                  <ActivityIndicator color="#c0392b" testID="show-more-loading" />
                ) : (
                  <Text style={styles.showMoreText}>{t.showMore}</Text>
                )}
              </TouchableOpacity>
            ) : null}
            {showMoreErrorMessage ? <ErrorBanner message={showMoreErrorMessage} /> : null}
          </View>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { padding: 16, backgroundColor: "#f5f5f5", flexGrow: 1 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 },
  heading: { fontSize: 22, fontWeight: "700" },
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
  showMoreButton: {
    backgroundColor: "#fff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#c0392b",
    padding: 12,
    alignItems: "center",
    marginTop: 8,
  },
  showMoreButtonDisabled: { opacity: 0.6 },
  showMoreText: { color: "#c0392b", fontWeight: "600", fontSize: 15 },
});

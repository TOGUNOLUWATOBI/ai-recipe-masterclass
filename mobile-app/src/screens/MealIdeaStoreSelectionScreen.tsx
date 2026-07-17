import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { getDiscountedRecipes } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import type { MealIdeasStackParamList } from "../navigation/types";
import { groupByStore } from "./StoresScreen";

// Epic E2: loads the same cached discount snapshot the Tilbud tab already reads
// (include_recipes=false -- a fast cache read, no LLM call) purely to list which
// stores currently have offers. Picking a store hands off to the results screen,
// which is the step that actually filters to recipe-eligible products (Task E2's hard
// rule: this screen itself must never trigger a new Tjek scan or reclassification).
export function MealIdeaStoreSelectionScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<MealIdeasStackParamList, "MealIdeasStoreSelection">>();
  const { t } = useLanguage();
  const [loading, setLoading] = useState(true);
  const [storeNames, setStoreNames] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const result = await getDiscountedRecipes(50, false);
      if (result.error) {
        setErrorMessage(result.error);
      } else {
        const groups = groupByStore(result.discounted_ingredients);
        setStoreNames(groups.map((g) => g.storeName));
      }
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <View style={styles.centered} testID="store-selection-loading">
        <ActivityIndicator size="large" color="#e63946" />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container} testID="meal-ideas-store-selection">
      {errorMessage ? <ErrorBanner message={errorMessage} /> : null}
      {!errorMessage && storeNames.length === 0 ? (
        <Text style={styles.emptyText}>{t.mealIdeasChooseStoreEmpty}</Text>
      ) : (
        storeNames.map((storeName) => (
          <TouchableOpacity
            key={storeName}
            style={styles.row}
            onPress={() => navigation.navigate("MealIdeasResults", { source: "store", storeName })}
            testID="store-selection-row"
          >
            <Text style={styles.rowText}>{storeName}</Text>
          </TouchableOpacity>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, backgroundColor: "#f5f5f5", flexGrow: 1 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f5f5f5" },
  row: { backgroundColor: "#fff", borderRadius: 12, padding: 16, marginBottom: 10 },
  rowText: { fontSize: 16, fontWeight: "600", color: "#1a1a1a" },
  emptyText: { textAlign: "center", marginTop: 40, color: "#666", fontSize: 14 },
});

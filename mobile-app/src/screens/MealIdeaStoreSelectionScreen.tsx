import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { getDiscountedRecipes } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import type { MealIdeasStackParamList } from "../navigation/types";
import { FALLBACK_STORE_LABEL, groupByStore } from "./StoresScreen";

// Same "no real store name" convention meal_ideas.py's resolve_store_items()/
// _discount_item_id() already use server-side -- must match exactly, since this is
// the value actually sent as the store_name filter. groupByStore()'s own
// FALLBACK_STORE_LABEL ("Other deals") is a *display* label only; translated back to
// this at navigation time below rather than sent to the backend as-is.
const UNKNOWN_STORE_VALUE = "unknown-store";

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

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);

    getDiscountedRecipes(50, false)
      .then((result) => {
        if (cancelled) return;
        if (result.error) {
          setErrorMessage(result.error);
          return;
        }
        // Only stores with at least one recipe_eligible offer -- a store whose
        // current offers are entirely non-food/ineligible would always land on the
        // results screen's empty state, a dead end this list can rule out up front.
        const groups = groupByStore(result.discounted_ingredients).filter((g) =>
          g.deals.some((d) => d.recipe_eligible)
        );
        setStoreNames(groups.map((g) => g.storeName));
      })
      .catch((err) => {
        if (!cancelled) setErrorMessage(userMessageForError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

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
            onPress={() =>
              navigation.navigate("MealIdeasResults", {
                source: "store",
                // groupByStore()'s display label must never be sent to the backend
                // as the actual store_name filter -- translate it back to the same
                // fallback value meal_ideas.py's resolve_store_items() already uses
                // for a null store_name, so this bucket can actually resolve there.
                storeName: storeName === FALLBACK_STORE_LABEL ? UNKNOWN_STORE_VALUE : storeName,
              })
            }
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

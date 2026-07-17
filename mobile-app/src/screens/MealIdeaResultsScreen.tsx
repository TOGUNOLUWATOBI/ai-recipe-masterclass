import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { getMealIdeasFromCart, getMealIdeasFromStore } from "../api/client";
import { userMessageForError } from "../api/errors";
import { useCart } from "../cart/CartContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import type { MealIdeasStackParamList } from "../navigation/types";
import type { MealIdea } from "../types/api";

const COMPLETION_LABEL_KEY = {
  complete: "mealIdeasCompletionComplete",
  nearly_complete: "mealIdeasCompletionNearlyComplete",
  partial: "mealIdeasCompletionPartial",
} as const;

const COMPLETION_COLOR: Record<MealIdea["completion_status"], string> = {
  complete: "#2e7d32",
  nearly_complete: "#b45309",
  partial: "#888888",
};

// Epic E4/E5: shows what a suggestion uses and what's still missing without ever
// implying the app knows a store's full inventory -- the missing-ingredients label
// differs by source (see missingLabel prop): the user's own cart can plainly say
// "still need", but a store-sourced idea must say "not found in the current offers"
// rather than "unavailable" (Task E5's hard requirement).
function MealIdeaCard({ idea, missingLabel }: { idea: MealIdea; missingLabel: string }) {
  const { t } = useLanguage();

  return (
    <View style={styles.card} testID="meal-idea-card">
      <View style={styles.cardHeaderRow}>
        <Text style={styles.cardTitle}>{idea.title ?? ""}</Text>
        <Text style={[styles.completionBadge, { color: COMPLETION_COLOR[idea.completion_status] }]}>
          {t[COMPLETION_LABEL_KEY[idea.completion_status]]}
        </Text>
      </View>

      {idea.selected_items_used.length > 0 ? (
        <Text style={styles.line}>
          <Text style={styles.lineLabel}>{t.mealIdeasUsesLabel} </Text>
          {idea.selected_items_used.join(", ")}
        </Text>
      ) : null}

      {idea.missing_required_ingredients.length > 0 ? (
        <Text style={styles.line} testID="meal-idea-missing">
          <Text style={styles.lineLabel}>{missingLabel} </Text>
          {idea.missing_required_ingredients.join(", ")}
        </Text>
      ) : null}

      {idea.optional_ingredients.length > 0 ? (
        <Text style={styles.line} testID="meal-idea-optional">
          <Text style={styles.lineLabel}>{t.mealIdeasOptionalLabel} </Text>
          {idea.optional_ingredients.map((ing) => ing.name).join(", ")}
        </Text>
      ) : null}

      {idea.pantry_basics_assumed.length > 0 ? (
        <Text style={styles.pantryNote}>{t.mealIdeasPantryBasicsNote(idea.pantry_basics_assumed.join(", "))}</Text>
      ) : null}
    </View>
  );
}

export function MealIdeaResultsScreen() {
  const route = useRoute<RouteProp<MealIdeasStackParamList, "MealIdeasResults">>();
  const { t, language } = useLanguage();
  const { items } = useCart();
  const [loading, setLoading] = useState(true);
  const [ideas, setIdeas] = useState<MealIdea[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Distinguishes "never had anything eligible to ask about" (cart flow only, see
  // below) from "asked, but nothing came back" -- these need different empty-state
  // copy: the former tells the user what to do (select an ingredient), the latter
  // doesn't, since they already selected something and there's no further action to
  // suggest.
  const [skippedEmptySelection, setSkippedEmptySelection] = useState(false);

  const params = route.params;

  // Only ever the items the user actually opted in for meal ideas (Epic B4's
  // selection, see CartContext.toggleMealIdeaSelection) -- an ineligible item can
  // never be selected in the first place, but this stays explicit rather than relying
  // on that invariant holding elsewhere. Memoized as a stable, order-independent
  // primitive (not the raw array) so the fetch effect below only re-runs when the
  // actual set of eligible+selected ids changes -- `items` itself gets a new array
  // reference on every cart mutation (quantity bumps, unrelated add/remove), and
  // depending on that directly would re-fetch on every one of those, even ones
  // unrelated to what's actually selected, and even for the store-sourced flow, which
  // never uses the cart at all.
  const eligibleSelectedIdsKey = useMemo(
    () =>
      JSON.stringify(
        items.filter((item) => item.recipe_eligible && item.selected_for_meal_ideas).map((item) => item.discount_item_id)
      ),
    [items]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setSkippedEmptySelection(false);

    async function load() {
      try {
        if (params.source === "cart") {
          const eligibleSelectedIds: string[] = JSON.parse(eligibleSelectedIdsKey);
          if (eligibleSelectedIds.length === 0) {
            if (!cancelled) {
              setIdeas([]);
              setSkippedEmptySelection(true);
            }
            return;
          }
          const response = await getMealIdeasFromCart(eligibleSelectedIds, 5, language);
          if (!cancelled) setIdeas(response.ideas);
        } else {
          const response = await getMealIdeasFromStore(params.storeName, 5, language);
          if (!cancelled) setIdeas(response.ideas);
        }
      } catch (err) {
        if (!cancelled) setErrorMessage(userMessageForError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
    // `language` is intentionally still a dependency for forward-compatibility, even
    // though meal_ideas.py doesn't translate ideas yet (see its own docstring) -- once
    // it does, a language change should refetch, same as every other endpoint here.
  }, [params, eligibleSelectedIdsKey, language]);

  const missingLabel = params.source === "cart" ? t.mealIdeasStillNeedLabel : t.mealIdeasNotFoundInOffersLabel;
  const sourceHeading = params.source === "cart" ? t.mealIdeasResultsFromCart : t.mealIdeasResultsFromStore(params.storeName);
  const emptyMessage =
    params.source === "cart"
      ? skippedEmptySelection
        ? t.mealIdeasEmptyCart
        : t.mealIdeasNoIdeasFound
      : t.mealIdeasEmptyStore(params.storeName);

  if (loading) {
    return (
      <View style={styles.centered} testID="meal-ideas-results-loading">
        <ActivityIndicator size="large" color="#e63946" />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container} testID="meal-ideas-results">
      <Text style={styles.sourceHeading}>{sourceHeading}</Text>

      {errorMessage ? <ErrorBanner message={errorMessage} /> : null}

      {!errorMessage && ideas.length === 0 ? (
        <Text style={styles.emptyText}>{emptyMessage}</Text>
      ) : (
        ideas.map((idea, index) => <MealIdeaCard key={index} idea={idea} missingLabel={missingLabel} />)
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, backgroundColor: "#f5f5f5", flexGrow: 1 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f5f5f5" },
  sourceHeading: { fontSize: 13, color: "#888", marginBottom: 12, fontStyle: "italic" },
  card: { backgroundColor: "#fff", borderRadius: 12, padding: 16, marginBottom: 12, gap: 4 },
  cardHeaderRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 4 },
  cardTitle: { fontSize: 16, fontWeight: "700", color: "#1a1a1a", flex: 1 },
  completionBadge: { fontSize: 12, fontWeight: "700" },
  line: { fontSize: 13, color: "#333", lineHeight: 19 },
  lineLabel: { fontWeight: "600", color: "#1a1a1a" },
  pantryNote: { fontSize: 12, color: "#888", fontStyle: "italic", marginTop: 4 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#666", fontSize: 14 },
});

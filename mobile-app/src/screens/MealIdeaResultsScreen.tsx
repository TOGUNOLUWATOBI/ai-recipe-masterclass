import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { getIngredientOffers, getMealIdeasFromCart, getMealIdeasFromStore } from "../api/client";
import { userMessageForError } from "../api/errors";
import { useCart } from "../cart/CartContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import type { MealIdeasStackParamList } from "../navigation/types";
import type { IngredientOffer, MealIdea } from "../types/api";

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

// Epic F5: how many offers /ingredient-offers returns per ingredient -- shown one at
// a time with a "view more" toggle (Task F6), so this just needs to cover the small
// initial list plus whatever a user might reasonably want to expand into.
const MAX_OFFERS_PER_INGREDIENT = 3;

function formatNok(value: number): string {
  return `${value.toFixed(2).replace(".", ",")} kr`;
}

// Epic F7: a fuzzy match is real but uncertain -- labeled rather than hidden, so the
// user still sees it but never mistakes it for a confirmed match.
function OfferRow({ offer }: { offer: IngredientOffer }) {
  const { t } = useLanguage();
  const hasDiscount = offer.discount_pct != null && offer.reference_price != null && offer.current_price != null;

  return (
    <View style={styles.offerRow} testID="ingredient-offer-row">
      <Text style={styles.offerText} numberOfLines={1}>
        {offer.original_product_name}
        {offer.store_name ? ` · ${offer.store_name}` : ""}
        {offer.match_confidence === "fuzzy" ? ` (${t.mealIdeasPossibleMatchLabel})` : ""}
      </Text>
      {offer.current_price != null ? (
        <View style={styles.offerPriceRow}>
          <Text style={styles.offerPrice}>{formatNok(offer.current_price)}</Text>
          {hasDiscount ? <Text style={styles.offerReferencePrice}>{formatNok(offer.reference_price as number)}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

function IngredientOfferStatus({ ingredientName, offers }: { ingredientName: string; offers: IngredientOffer[] | undefined }) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);

  if (!offers || offers.length === 0) {
    return (
      <View style={styles.ingredientOfferBlock}>
        <Text style={styles.ingredientOfferName}>{ingredientName}</Text>
        <Text style={styles.noOfferText} testID="no-offer-found">
          {t.mealIdeasNoOfferFound}
        </Text>
      </View>
    );
  }

  const visibleOffers = expanded ? offers : offers.slice(0, 1);
  const remaining = offers.length - visibleOffers.length;

  return (
    <View style={styles.ingredientOfferBlock}>
      <Text style={styles.ingredientOfferName}>{ingredientName}</Text>
      {visibleOffers.map((offer, index) => (
        <OfferRow key={index} offer={offer} />
      ))}
      {remaining > 0 ? (
        <TouchableOpacity onPress={() => setExpanded(true)} testID="view-more-offers">
          <Text style={styles.viewMoreText}>{t.mealIdeasViewMoreOffers(remaining)}</Text>
        </TouchableOpacity>
      ) : null}
      {expanded && offers.length > 1 ? (
        <TouchableOpacity onPress={() => setExpanded(false)}>
          <Text style={styles.viewMoreText}>{t.mealIdeasShowFewerOffers}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

// Epic E4/E5: shows what a suggestion uses and what's still missing without ever
// implying the app knows a store's full inventory -- the missing-ingredients label
// differs by source (see missingLabel prop): the user's own cart can plainly say
// "still need", but a store-sourced idea must say "not found in the current offers"
// rather than "unavailable" (Task E5's hard requirement).
function MealIdeaCard({
  idea,
  missingLabel,
  offersByIngredient,
}: {
  idea: MealIdea;
  missingLabel: string;
  offersByIngredient: Record<string, IngredientOffer[]>;
}) {
  const { t } = useLanguage();
  // Epic F5: "On offer this week" covers both required and optional ingredients --
  // deduped, since the same name could in principle appear in both lists.
  const onOfferIngredientNames = useMemo(() => {
    const seen = new Set<string>();
    const names: string[] = [];
    for (const ing of [...idea.required_ingredients, ...idea.optional_ingredients]) {
      if (seen.has(ing.name)) continue;
      seen.add(ing.name);
      names.push(ing.name);
    }
    return names;
  }, [idea.required_ingredients, idea.optional_ingredients]);

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

      {onOfferIngredientNames.length > 0 ? (
        <View style={styles.onOfferSection} testID="on-offer-section">
          <Text style={styles.onOfferHeading}>{t.mealIdeasOnOfferHeading}</Text>
          {onOfferIngredientNames.map((name) => (
            <IngredientOfferStatus key={name} ingredientName={name} offers={offersByIngredient[name]} />
          ))}
        </View>
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
  // Epic F5: keyed by ingredient name -- a best-effort enhancement layered on top of
  // the ideas themselves, so a failed/slow lookup never blocks or errors the meal
  // ideas the user actually asked for (same "best-effort, never a hard error"
  // convention as CartScreen's own expiry check).
  const [offersByIngredient, setOffersByIngredient] = useState<Record<string, IngredientOffer[]>>({});

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

  // Epic F5: once the ideas themselves are in, fetch current offers for every
  // required/optional ingredient across all of them in one batched call (Task F4) --
  // never per-card, never per-render. Best-effort: a failed lookup just leaves
  // offersByIngredient empty (every card shows "no current offer found"), it never
  // surfaces as a screen-level error or blocks the ideas themselves from showing.
  useEffect(() => {
    let cancelled = false;
    if (ideas.length === 0) {
      setOffersByIngredient({});
      return;
    }

    const seen = new Set<string>();
    const names: string[] = [];
    for (const idea of ideas) {
      for (const ing of [...idea.required_ingredients, ...idea.optional_ingredients]) {
        if (seen.has(ing.name)) continue;
        seen.add(ing.name);
        names.push(ing.name);
      }
    }

    getIngredientOffers(names, MAX_OFFERS_PER_INGREDIENT)
      .then((response) => {
        if (cancelled) return;
        const byName: Record<string, IngredientOffer[]> = {};
        for (const entry of response.ingredients) {
          byName[entry.ingredient] = entry.offers;
        }
        setOffersByIngredient(byName);
      })
      .catch(() => {
        if (!cancelled) setOffersByIngredient({});
      });

    return () => {
      cancelled = true;
    };
  }, [ideas]);

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
        ideas.map((idea, index) => (
          <MealIdeaCard key={index} idea={idea} missingLabel={missingLabel} offersByIngredient={offersByIngredient} />
        ))
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
  onOfferSection: { marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: "#f0f0f0", gap: 8 },
  onOfferHeading: { fontSize: 12, fontWeight: "700", color: "#1a1a1a", textTransform: "uppercase", letterSpacing: 0.3 },
  ingredientOfferBlock: { gap: 2 },
  ingredientOfferName: { fontSize: 12, fontWeight: "600", color: "#555" },
  noOfferText: { fontSize: 12, color: "#999", fontStyle: "italic" },
  offerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  offerText: { fontSize: 13, color: "#333", flex: 1 },
  offerPriceRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  offerPrice: { fontSize: 13, fontWeight: "700", color: "#e63946" },
  offerReferencePrice: { fontSize: 11, color: "#999", textDecorationLine: "line-through" },
  viewMoreText: { fontSize: 12, color: "#e63946", fontWeight: "600" },
});

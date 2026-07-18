import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { getIngredientOffers, getMealIdeasFromCart, getMealIdeasFromStore, submitMealIdeaFeedback } from "../api/client";
import { userMessageForError } from "../api/errors";
import { useCart } from "../cart/CartContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { useLanguage } from "../i18n/LanguageContext";
import { translations } from "../i18n/translations";
import type { MealIdeasStackParamList } from "../navigation/types";
import type { IngredientOffer, MealIdea, MealIdeaFeedbackReason } from "../types/api";

// Only the plain-string translation keys -- excludes the ones typed as functions
// (e.g. mealIdeasViewMoreOffers), which Text can't render directly.
type StringTranslationKey = {
  [K in keyof typeof translations.en]: (typeof translations.en)[K] extends string ? K : never;
}[keyof typeof translations.en];

// Epic J3: the six fixed reasons the change spec calls out for a "Not helpful" tap --
// order matches the story's own listing. Keyed to translations.ts entries below.
const FEEDBACK_REASONS: { reason: MealIdeaFeedbackReason; labelKey: StringTranslationKey }[] = [
  { reason: "strange_combination", labelKey: "mealIdeasFeedbackReasonStrangeCombination" },
  { reason: "too_many_missing_ingredients", labelKey: "mealIdeasFeedbackReasonTooManyMissingIngredients" },
  { reason: "too_complicated", labelKey: "mealIdeasFeedbackReasonTooComplicated" },
  { reason: "incorrect_product", labelKey: "mealIdeasFeedbackReasonIncorrectProduct" },
  { reason: "not_an_everyday_meal", labelKey: "mealIdeasFeedbackReasonNotAnEverydayMeal" },
  { reason: "ingredient_availability_was_wrong", labelKey: "mealIdeasFeedbackReasonIngredientAvailabilityWasWrong" },
];

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

// Epic J3: a quick "Helpful"/"Not helpful" tap on this one idea, stored alongside its
// own output (see api/client.ts's submitMealIdeaFeedback()). "Not helpful" reveals the
// six fixed reason chips (multi-select, optional) before actually submitting, so
// exactly one feedback row is ever written per card -- not one row per chip tap.
function MealIdeaFeedbackControl({
  idea,
  requestId,
  recommendationType,
}: {
  idea: MealIdea;
  requestId: string;
  recommendationType: "cart" | "store";
}) {
  const { t } = useLanguage();
  const [stage, setStage] = useState<"idle" | "choosing_reasons" | "submitted">("idle");
  const [selectedReasons, setSelectedReasons] = useState<Set<MealIdeaFeedbackReason>>(new Set());

  function submit(helpful: boolean, reasons: MealIdeaFeedbackReason[]) {
    setStage("submitted");
    submitMealIdeaFeedback(
      requestId,
      recommendationType,
      idea.title,
      helpful,
      reasons,
      idea.selected_items_used,
      idea.missing_required_ingredients,
      idea.source_type
    );
  }

  function toggleReason(reason: MealIdeaFeedbackReason) {
    setSelectedReasons((prev) => {
      const next = new Set(prev);
      if (next.has(reason)) next.delete(reason);
      else next.add(reason);
      return next;
    });
  }

  if (stage === "submitted") {
    return (
      <View style={styles.feedbackSection}>
        <Text style={styles.feedbackThanks} testID="meal-idea-feedback-thanks">
          {t.mealIdeasFeedbackThanks}
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.feedbackSection}>
      <View style={styles.feedbackRow}>
        <Text style={styles.feedbackPrompt}>{t.mealIdeasFeedbackPrompt}</Text>
        <TouchableOpacity
          onPress={() => submit(true, [])}
          style={styles.feedbackButton}
          testID="meal-idea-feedback-helpful"
        >
          <Text style={styles.feedbackButtonText}>{t.mealIdeasFeedbackHelpful}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setStage("choosing_reasons")}
          style={styles.feedbackButton}
          testID="meal-idea-feedback-not-helpful"
        >
          <Text style={styles.feedbackButtonText}>{t.mealIdeasFeedbackNotHelpful}</Text>
        </TouchableOpacity>
      </View>

      {stage === "choosing_reasons" ? (
        <View style={styles.feedbackReasons} testID="meal-idea-feedback-reasons">
          <View style={styles.reasonChipRow}>
            {FEEDBACK_REASONS.map(({ reason, labelKey }) => {
              const isSelected = selectedReasons.has(reason);
              return (
                <TouchableOpacity
                  key={reason}
                  onPress={() => toggleReason(reason)}
                  style={[styles.reasonChip, isSelected && styles.reasonChipSelected]}
                  testID={`meal-idea-feedback-reason-${reason}`}
                >
                  <Text style={[styles.reasonChipText, isSelected && styles.reasonChipTextSelected]}>{t[labelKey]}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TouchableOpacity
            onPress={() => submit(false, Array.from(selectedReasons))}
            style={styles.feedbackSubmitButton}
            testID="meal-idea-feedback-submit"
          >
            <Text style={styles.feedbackSubmitButtonText}>{t.mealIdeasFeedbackSubmit}</Text>
          </TouchableOpacity>
        </View>
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
  requestId,
  recommendationType,
}: {
  idea: MealIdea;
  missingLabel: string;
  offersByIngredient: Record<string, IngredientOffer[]>;
  requestId: string;
  recommendationType: "cart" | "store";
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

      <MealIdeaFeedbackControl idea={idea} requestId={requestId} recommendationType={recommendationType} />
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
  // Epic J3: needed to correlate a later "Helpful"/"Not helpful" tap back to the
  // request that produced these specific ideas (see submitMealIdeaFeedback()).
  const [requestId, setRequestId] = useState<string | null>(null);

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
          if (!cancelled) {
            setIdeas(response.ideas);
            setRequestId(response.request_id);
          }
        } else {
          const response = await getMealIdeasFromStore(params.storeName, 5, language);
          if (!cancelled) {
            setIdeas(response.ideas);
            setRequestId(response.request_id);
          }
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
          <MealIdeaCard
            key={index}
            idea={idea}
            missingLabel={missingLabel}
            offersByIngredient={offersByIngredient}
            requestId={requestId ?? ""}
            recommendationType={params.source}
          />
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
  feedbackSection: { marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: "#f0f0f0", gap: 8 },
  feedbackRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  feedbackPrompt: { fontSize: 12, color: "#666", flex: 1 },
  feedbackButton: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 16, backgroundColor: "#f0f0f0" },
  feedbackButtonText: { fontSize: 12, fontWeight: "600", color: "#333" },
  feedbackThanks: { fontSize: 12, color: "#2e7d32", fontWeight: "600" },
  feedbackReasons: { gap: 8 },
  reasonChipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  reasonChip: { paddingVertical: 5, paddingHorizontal: 10, borderRadius: 14, borderWidth: 1, borderColor: "#ddd" },
  reasonChipSelected: { backgroundColor: "#fdecea", borderColor: "#e63946" },
  reasonChipText: { fontSize: 11, color: "#555" },
  reasonChipTextSelected: { color: "#e63946", fontWeight: "600" },
  feedbackSubmitButton: { alignSelf: "flex-start", paddingVertical: 6, paddingHorizontal: 14, borderRadius: 16, backgroundColor: "#e63946" },
  feedbackSubmitButtonText: { fontSize: 12, fontWeight: "700", color: "#fff" },
});

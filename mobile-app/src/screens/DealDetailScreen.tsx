import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { getRecipesFromIngredients } from "../api/client";
import { userMessageForError } from "../api/errors";
import { MAX_INGREDIENT_COUNT } from "../api/validation";
import { AddToCartButton } from "../components/AddToCartButton";
import { ErrorBanner } from "../components/ErrorBanner";
import { RecipeCard } from "../components/RecipeCard";
import { useLanguage } from "../i18n/LanguageContext";
import type { TilbudStackParamList } from "../navigation/types";
import type { IngredientsResponse } from "../types/api";

function formatNok(value: number): string {
  return `${value.toFixed(2).replace(".", ",")} kr`;
}

export function DealDetailScreen() {
  const route = useRoute<RouteProp<TilbudStackParamList, "DealDetail">>();
  const { language, t } = useLanguage();
  const { deal } = route.params;

  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<IngredientsResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showMoreLoading, setShowMoreLoading] = useState(false);
  const [canShowMore, setCanShowMore] = useState(false);
  const [showMoreErrorMessage, setShowMoreErrorMessage] = useState<string | null>(null);

  // Recipe generation happens on demand for exactly the one product tapped, reusing the
  // already-tested /recipes/from-ingredients endpoint — cheaper and far faster than
  // generating recipes for every discounted item up front when only one gets viewed.
  //
  // The initial request only asks for 1 recipe: the backend's fallback-generation path
  // is hard-capped at 3 sequential LLM calls no matter what max_results is requested, so
  // asking for 1 up front turns a ~97s worst case into ~32s. Further recipes are fetched
  // lazily via the "Show more" button below (see handleShowMore) — the response for a
  // larger max_results is a prefix-stable superset of a smaller one, so it's always safe
  // to replace `result` with the new response wholesale.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    setCanShowMore(false);
    setShowMoreErrorMessage(null);
    getRecipesFromIngredients([deal.product_name], 1, true, language)
      .then((response) => {
        if (cancelled) return;
        if (response.error) {
          setErrorMessage(response.error);
        } else {
          setResult(response);
          setCanShowMore(response.recipes.length > 0 && response.recipes.length < MAX_INGREDIENT_COUNT);
        }
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
  }, [deal.product_name, language]);

  // "Show more" re-requests the same product with a larger max_results, one more than
  // what's currently shown. It never disturbs the already-rendered cards or the
  // full-screen spinner — only the button itself reflects the in-flight request. The
  // button hides itself once a request stops returning more recipes than before, which
  // generically covers both real backend caps (the generated-fallback path hard-stops at
  // 3 total; the corpus path stops whenever no further matches clear the relevance
  // threshold) without hardcoding either number here.
  const handleShowMore = useCallback(() => {
    if (!result || showMoreLoading) return;
    const previousCount = result.recipes.length;
    const nextMax = Math.min(previousCount + 1, MAX_INGREDIENT_COUNT);
    setShowMoreLoading(true);
    setShowMoreErrorMessage(null);
    getRecipesFromIngredients([deal.product_name], nextMax, true, language)
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
  }, [deal.product_name, result, showMoreLoading, language]);

  // The backend now returns every product per store, not just confirmed discounts --
  // reference_price/discount_pct are only present when a real, meaningful drop was
  // actually computed (see grocery_discounts.py), so the strike-through price and
  // badge only render then.
  const hasDiscount = deal.discount_pct != null && deal.reference_price != null;

  return (
    <ScrollView contentContainerStyle={styles.container} testID="deal-detail-screen">
      <View style={styles.hero}>
        {deal.image_url ? (
          <Image source={{ uri: deal.image_url }} style={styles.heroImage} resizeMode="contain" />
        ) : null}
        <Text style={styles.productName}>{deal.product_name}</Text>
        {deal.store_name ? <Text style={styles.storeName}>{deal.store_name}</Text> : null}
        <View style={styles.priceRow}>
          <Text style={[styles.price, !hasDiscount && styles.priceNoDiscount]}>{formatNok(deal.current_price)}</Text>
          {hasDiscount ? (
            <>
              <Text style={styles.referencePrice}>{formatNok(deal.reference_price as number)}</Text>
              <Text style={styles.discountBadge}>-{Math.round(deal.discount_pct as number)}%</Text>
            </>
          ) : null}
        </View>
        <AddToCartButton deal={deal} />
      </View>

      <Text style={styles.recipesHeading}>{t.dealDetailRecipesWith(deal.product_name)}</Text>

      {loading ? (
        <ActivityIndicator size="large" color="#e63946" style={styles.spinner} testID="deal-detail-loading" />
      ) : errorMessage ? (
        <ErrorBanner message={errorMessage} />
      ) : result && result.recipes.length > 0 ? (
        <>
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
                <ActivityIndicator color="#e63946" testID="show-more-loading" />
              ) : (
                <Text style={styles.showMoreText}>{t.showMore}</Text>
              )}
            </TouchableOpacity>
          ) : null}
          {showMoreErrorMessage ? <ErrorBanner message={showMoreErrorMessage} /> : null}
        </>
      ) : (
        <Text style={styles.emptyText}>{t.dealDetailEmpty}</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, backgroundColor: "#f5f5f5", flexGrow: 1 },
  hero: { backgroundColor: "#fff", borderRadius: 12, padding: 16, alignItems: "center", marginBottom: 20 },
  heroImage: { width: 140, height: 140, marginBottom: 12 },
  productName: { fontSize: 18, fontWeight: "700", textAlign: "center", color: "#1a1a1a" },
  storeName: { fontSize: 13, color: "#888", marginTop: 2 },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 10 },
  price: { fontSize: 22, fontWeight: "800", color: "#e63946" },
  priceNoDiscount: { color: "#1a1a1a" },
  referencePrice: { fontSize: 14, color: "#999", textDecorationLine: "line-through" },
  discountBadge: {
    backgroundColor: "#e63946",
    color: "#fff",
    fontWeight: "700",
    fontSize: 12,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    overflow: "hidden",
  },
  recipesHeading: { fontSize: 16, fontWeight: "700", marginBottom: 10, color: "#1a1a1a" },
  spinner: { marginTop: 20 },
  emptyText: { color: "#666", fontSize: 14, fontStyle: "italic" },
  showMoreButton: {
    backgroundColor: "#fff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e63946",
    padding: 12,
    alignItems: "center",
    marginTop: 8,
  },
  showMoreButtonDisabled: { opacity: 0.6 },
  showMoreText: { color: "#e63946", fontWeight: "600", fontSize: 15 },
});

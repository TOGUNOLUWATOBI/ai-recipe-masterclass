import type { RouteProp } from "@react-navigation/native";
import { useRoute } from "@react-navigation/native";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, View } from "react-native";
import { getRecipesFromIngredients } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { RecipeCard } from "../components/RecipeCard";
import type { TilbudStackParamList } from "../navigation/types";
import type { IngredientsResponse } from "../types/api";

function formatNok(value: number): string {
  return `${value.toFixed(2).replace(".", ",")} kr`;
}

export function DealDetailScreen() {
  const route = useRoute<RouteProp<TilbudStackParamList, "DealDetail">>();
  const { deal } = route.params;

  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<IngredientsResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Recipe generation happens on demand for exactly the one product tapped, reusing the
  // already-tested /recipes/from-ingredients endpoint — cheaper and far faster than
  // generating recipes for every discounted item up front when only one gets viewed.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    getRecipesFromIngredients([deal.product_name], 5)
      .then((response) => {
        if (cancelled) return;
        if (response.error) {
          setErrorMessage(response.error);
        } else {
          setResult(response);
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
  }, [deal.product_name]);

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
      </View>

      <Text style={styles.recipesHeading}>Oppskrifter med {deal.category}</Text>

      {loading ? (
        <ActivityIndicator size="large" color="#e63946" style={styles.spinner} testID="deal-detail-loading" />
      ) : errorMessage ? (
        <ErrorBanner message={errorMessage} />
      ) : result && result.recipes.length > 0 ? (
        result.recipes.map((recipe, index) => <RecipeCard key={index} title={recipe.title} text={recipe.text} />)
      ) : (
        <Text style={styles.emptyText}>Fant ingen oppskrifter for denne varen.</Text>
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
});

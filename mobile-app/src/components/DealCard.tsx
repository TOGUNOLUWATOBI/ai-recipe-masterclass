import React from "react";
import { Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { Text } from "./AppText";
import type { DiscountedProduct } from "../types/api";
import { FONT_BOLD } from "../theme/typography";
import { AddToCartButton } from "./AddToCartButton";

function formatNok(value: number): string {
  return `${value.toFixed(2).replace(".", ",")} kr`;
}

interface DealCardProps {
  deal: DiscountedProduct;
  onPress: () => void;
}

export function DealCard({ deal, onPress }: DealCardProps) {
  // The backend now returns every product per store, not just confirmed discounts
  // (see grocery_discounts.py — no official sale flag exists, and many products lack
  // enough price history to evaluate at all) — discount_pct/reference_price are only
  // present when a real, meaningful drop was actually computed, so the badge and
  // strike-through price only render then, never as a misleading "0% off".
  const hasDiscount = deal.discount_pct != null && deal.reference_price != null;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7} testID="deal-card">
      {hasDiscount ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>-{Math.round(deal.discount_pct as number)}%</Text>
        </View>
      ) : null}
      {deal.image_url ? (
        <Image source={{ uri: deal.image_url }} style={styles.image} resizeMode="contain" />
      ) : (
        <View style={[styles.image, styles.imagePlaceholder]}>
          <Text style={styles.imagePlaceholderText}>🛒</Text>
        </View>
      )}
      <Text style={styles.name} numberOfLines={2}>
        {deal.product_name}
      </Text>
      {deal.unit_price != null ? (
        <Text style={styles.unitPrice}>
          {formatNok(deal.unit_price)}/{deal.unit_price_unit ?? "unit"}
        </Text>
      ) : null}
      <View style={styles.priceColumn}>
        <Text style={[styles.price, !hasDiscount && styles.priceNoDiscount]} numberOfLines={1}>
          {formatNok(deal.current_price)}
        </Text>
        {hasDiscount ? (
          <Text style={styles.referencePrice} numberOfLines={1}>
            {formatNok(deal.reference_price as number)}
          </Text>
        ) : null}
      </View>
      {/* Nested TouchableOpacity: React Native's touch responder system grants the
          gesture to whichever view claims it (here, the button/stepper inside), so
          tapping this never also fires the card's own onPress/navigation. */}
      <AddToCartButton deal={deal} compact />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    width: "100%",
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 10,
    boxShadow: "0px 1px 3px rgba(0, 0, 0, 0.08)",
    elevation: 2,
    overflow: "hidden",
  },
  badge: {
    position: "absolute",
    top: 8,
    left: 8,
    backgroundColor: "#e63946",
    borderRadius: 20,
    paddingHorizontal: 8,
    paddingVertical: 3,
    zIndex: 1,
  },
  badgeText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  image: { width: "100%", height: 90, borderRadius: 8, marginBottom: 8, backgroundColor: "#f5f5f5" },
  imagePlaceholder: { alignItems: "center", justifyContent: "center" },
  imagePlaceholderText: { fontSize: 28 },
  // Tjek headings arrive in whatever case each merchant happened to submit (some
  // ALL CAPS, some Title Case, some sentence case) -- textTransform normalizes the
  // *display* only, never the underlying string, so screen readers/search/cart
  // matching still see the real product_name untouched.
  name: {
    fontSize: 13,
    fontWeight: "600",
    fontFamily: FONT_BOLD,
    color: "#1a1a1a",
    minHeight: 34,
    overflow: "hidden",
    textTransform: "uppercase",
  },
  unitPrice: { fontSize: 11, color: "#888", marginTop: 2 },
  priceColumn: { marginTop: 6 },
  price: { fontSize: 17, fontWeight: "800", fontFamily: FONT_BOLD, color: "#e63946" },
  priceNoDiscount: { color: "#1a1a1a" },
  referencePrice: { fontSize: 12, color: "#999", textDecorationLine: "line-through", marginTop: 2 },
});

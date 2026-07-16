import { Ionicons } from "@expo/vector-icons";
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getDiscountedRecipes } from "../api/client";
import { useCart } from "../cart/CartContext";
import { useLanguage } from "../i18n/LanguageContext";
import { cartItemIdFor, type CartItem } from "../types/cart";

function formatNok(value: number): string {
  return `${value.toFixed(2).replace(".", ",")} kr`;
}

export function CartScreen() {
  const insets = useSafeAreaInsets();
  const { language, t } = useLanguage();
  const {
    items,
    foodItems,
    nonFoodItems,
    mealIdeaSelectedCount,
    incrementQuantity,
    decrementQuantity,
    removeItem,
    toggleMealIdeaSelection,
    clearCart,
  } = useCart();

  // Epic B6: cross-references the cart against the latest cached discount snapshot (a
  // fast cache read, never a live Tjek scan -- see api/client.ts's include_recipes=false
  // path) so an item whose offer has dropped out of the current scan gets flagged
  // rather than continuing to imply its stored price/discount is still current.
  // Best-effort: a failed fetch just means nothing gets flagged as expired this
  // session -- never a hard error blocking the cart itself from being usable.
  const [currentOfferIds, setCurrentOfferIds] = useState<Set<string> | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDiscountedRecipes(10, false, language)
      .then((response) => {
        if (cancelled) return;
        setCurrentOfferIds(new Set(response.discounted_ingredients.map((d) => cartItemIdFor(d))));
      })
      .catch(() => {
        if (!cancelled) setCurrentOfferIds(null);
      });
    return () => {
      cancelled = true;
    };
  }, [language]);

  const handleClearCart = useCallback(() => {
    Alert.alert(t.clearCartConfirmTitle, t.clearCartConfirmMessage, [
      { text: t.cancel, style: "cancel" },
      { text: t.clearCart, style: "destructive", onPress: clearCart },
    ]);
  }, [clearCart, t]);

  const hasEligibleItems = items.some((item) => item.recipe_eligible);

  if (items.length === 0) {
    return (
      <View style={[styles.container, styles.centered, { paddingTop: insets.top + 16 }]} testID="cart-empty-state">
        <Ionicons name="cart-outline" size={48} color="#ccc" />
        <Text style={styles.emptyText}>{t.cartEmpty}</Text>
      </View>
    );
  }

  const sections: { key: string; label: string; items: CartItem[] }[] = [
    { key: "food", label: t.foodTab, items: foodItems },
    { key: "non_food", label: t.nonFoodTab, items: nonFoodItems },
  ].filter((section) => section.items.length > 0);
  // Only label sections when the cart actually mixes food and non-food -- same
  // reasoning as StoreItemsScreen's Food/Snacks split: an all-one-type cart just
  // shows its list with no redundant lone header.
  const showSectionHeaders = sections.length > 1;

  return (
    <View style={styles.container} testID="cart-screen">
      <View style={[styles.headerRow, { paddingTop: insets.top + 16 }]}>
        <Text style={styles.heading}>{t.tabCart}</Text>
        <TouchableOpacity onPress={handleClearCart} testID="clear-cart-button">
          <Text style={styles.clearCartText}>{t.clearCart}</Text>
        </TouchableOpacity>
      </View>

      {hasEligibleItems ? (
        <Text style={styles.selectionSummary} testID="meal-idea-selection-summary">
          {t.ingredientsSelectedForMealIdeas(mealIdeaSelectedCount)}
        </Text>
      ) : null}

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {sections.map((section) => (
          <View key={section.key}>
            {showSectionHeaders ? <Text style={styles.sectionHeader}>{section.label}</Text> : null}
            {section.items.map((item) => {
              const isExpired = currentOfferIds != null && !currentOfferIds.has(item.cart_item_id);
              const hasDiscount = !isExpired && item.reference_price != null;

              return (
                <View key={item.cart_item_id} style={styles.row} testID="cart-item-row">
                  {item.image_url ? (
                    <Image source={{ uri: item.image_url }} style={styles.rowImage} resizeMode="contain" />
                  ) : (
                    <View style={[styles.rowImage, styles.rowImagePlaceholder]}>
                      <Text style={styles.rowImagePlaceholderText}>🛒</Text>
                    </View>
                  )}

                  <View style={styles.rowDetails}>
                    <Text style={styles.rowName} numberOfLines={2}>
                      {item.product_name}
                    </Text>
                    {item.store_name ? <Text style={styles.rowStore}>{item.store_name}</Text> : null}
                    <View style={styles.rowPriceRow}>
                      <Text style={styles.rowPrice}>{formatNok(item.current_price)}</Text>
                      {hasDiscount ? (
                        <Text style={styles.rowReferencePrice}>{formatNok(item.reference_price as number)}</Text>
                      ) : null}
                    </View>
                    {isExpired ? (
                      <Text style={styles.expiredBadge} testID="expired-badge">
                        {t.offerMayBeExpired}
                      </Text>
                    ) : null}

                    {item.recipe_eligible ? (
                      <TouchableOpacity
                        style={styles.mealIdeaToggleRow}
                        onPress={() => toggleMealIdeaSelection(item.cart_item_id)}
                        testID="meal-idea-toggle"
                      >
                        <Ionicons
                          name={item.selected_for_meal_ideas ? "checkbox" : "square-outline"}
                          size={18}
                          color="#e63946"
                        />
                        <Text style={styles.mealIdeaToggleText}>{t.useForMealIdeas}</Text>
                      </TouchableOpacity>
                    ) : (
                      <Text style={styles.notUsedText}>{t.notUsedForMealIdeas}</Text>
                    )}
                  </View>

                  <View style={styles.rowActions}>
                    <TouchableOpacity onPress={() => removeItem(item.cart_item_id)} testID="cart-remove-button">
                      <Ionicons name="close" size={18} color="#999" />
                    </TouchableOpacity>
                    <View style={styles.stepper}>
                      <TouchableOpacity
                        style={styles.stepperButton}
                        onPress={() => decrementQuantity(item.cart_item_id)}
                        testID="cart-decrement-button"
                      >
                        <Ionicons name="remove" size={14} color="#e63946" />
                      </TouchableOpacity>
                      <Text style={styles.stepperQuantity} testID="cart-item-quantity">
                        {item.quantity}
                      </Text>
                      <TouchableOpacity
                        style={styles.stepperButton}
                        onPress={() => incrementQuantity(item.cart_item_id)}
                        testID="cart-increment-button"
                      >
                        <Ionicons name="add" size={14} color="#e63946" />
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              );
            })}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  centered: { alignItems: "center", justifyContent: "center", gap: 12, paddingHorizontal: 32 },
  emptyText: { color: "#666", fontSize: 14, textAlign: "center" },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  heading: { fontSize: 26, fontWeight: "800", color: "#1a1a1a" },
  clearCartText: { color: "#e63946", fontWeight: "600", fontSize: 13 },
  selectionSummary: { fontSize: 13, color: "#666", paddingHorizontal: 16, marginBottom: 8 },
  scrollContent: { padding: 12, paddingBottom: 24 },
  sectionHeader: { fontSize: 18, fontWeight: "700", color: "#1a1a1a", marginTop: 12, marginBottom: 8, marginHorizontal: 4 },
  row: {
    flexDirection: "row",
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 10,
    marginBottom: 10,
    gap: 10,
    alignItems: "flex-start",
  },
  rowImage: { width: 56, height: 56, borderRadius: 8, backgroundColor: "#f5f5f5" },
  rowImagePlaceholder: { alignItems: "center", justifyContent: "center" },
  rowImagePlaceholderText: { fontSize: 22 },
  rowDetails: { flex: 1, gap: 3 },
  rowName: { fontSize: 14, fontWeight: "600", color: "#1a1a1a" },
  rowStore: { fontSize: 11, color: "#888" },
  rowPriceRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 2 },
  rowPrice: { fontSize: 14, fontWeight: "700", color: "#e63946" },
  rowReferencePrice: { fontSize: 12, color: "#999", textDecorationLine: "line-through" },
  expiredBadge: { fontSize: 11, color: "#b45309", fontStyle: "italic", marginTop: 2 },
  mealIdeaToggleRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 },
  mealIdeaToggleText: { fontSize: 12, color: "#1a1a1a" },
  notUsedText: { fontSize: 11, color: "#999", fontStyle: "italic", marginTop: 6 },
  rowActions: { alignItems: "flex-end", gap: 8 },
  stepper: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e63946",
  },
  stepperButton: { paddingHorizontal: 8, paddingVertical: 6 },
  stepperQuantity: { fontWeight: "700", fontSize: 13, color: "#1a1a1a", minWidth: 18, textAlign: "center" },
});

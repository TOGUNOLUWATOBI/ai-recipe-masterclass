import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useCart } from "../cart/CartContext";
import { useLanguage } from "../i18n/LanguageContext";
import type { DiscountedProduct } from "../types/api";
import { cartItemIdFor } from "../types/cart";

interface AddToCartButtonProps {
  deal: DiscountedProduct;
  // DealCard renders this inside a tight grid cell; DealDetailScreen has a full-width
  // hero area to work with. Same behavior either way, just sized differently.
  compact?: boolean;
}

/**
 * Epic B1's "Add to cart" control: shows a plain "Add to cart" button until the
 * product is in the cart, then morphs into a quantity stepper -- this is the
 * "clearly change state after selection" + "optional quantity controls" requirement
 * folded into one control rather than two separate pieces of UI. Used inside
 * DealCard (covers both the discount cards and the store item grid, since DealCard is
 * what renders there) and DealDetailScreen (the detail page) -- see the change spec's
 * Task B1 for why both need it: users shouldn't have to open the recipe generator
 * just to add something to their cart.
 */
export function AddToCartButton({ deal, compact = false }: AddToCartButtonProps) {
  const { getQuantity, addItem, incrementQuantity, decrementQuantity } = useCart();
  const { t } = useLanguage();
  const quantity = getQuantity(deal);
  const cartItemId = cartItemIdFor(deal);

  if (quantity === 0) {
    return (
      <TouchableOpacity
        style={[styles.addButton, compact && styles.addButtonCompact]}
        onPress={() => addItem(deal)}
        activeOpacity={0.7}
        testID="add-to-cart-button"
      >
        <Ionicons name="cart-outline" size={compact ? 14 : 16} color="#e63946" />
        <Text style={[styles.addButtonText, compact && styles.addButtonTextCompact]}>{t.addToCart}</Text>
      </TouchableOpacity>
    );
  }

  return (
    <View style={[styles.stepper, compact && styles.stepperCompact]} testID="cart-quantity-stepper">
      <TouchableOpacity
        style={styles.stepperButton}
        onPress={() => decrementQuantity(cartItemId)}
        activeOpacity={0.7}
        testID="decrement-quantity-button"
      >
        <Ionicons name="remove" size={compact ? 14 : 16} color="#e63946" />
      </TouchableOpacity>
      <Text style={styles.stepperQuantity} testID="cart-quantity">
        {quantity}
      </Text>
      <TouchableOpacity
        style={styles.stepperButton}
        onPress={() => incrementQuantity(cartItemId)}
        activeOpacity={0.7}
        testID="increment-quantity-button"
      >
        <Ionicons name="add" size={compact ? 14 : 16} color="#e63946" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  addButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: 8,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e63946",
    backgroundColor: "#fff",
  },
  addButtonCompact: { marginTop: 6, paddingVertical: 6, gap: 4 },
  addButtonText: { color: "#e63946", fontWeight: "700", fontSize: 14 },
  addButtonTextCompact: { fontSize: 11 },
  stepper: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e63946",
    backgroundColor: "#fff",
  },
  stepperCompact: { marginTop: 6 },
  stepperButton: { paddingHorizontal: 12, paddingVertical: 8, alignItems: "center", justifyContent: "center" },
  stepperQuantity: { fontWeight: "700", fontSize: 14, color: "#1a1a1a", minWidth: 20, textAlign: "center" },
});

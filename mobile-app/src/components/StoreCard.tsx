import React from "react";
import { Image, StyleSheet, Text, TouchableOpacity, View } from "react-native";

interface StoreCardProps {
  storeName: string;
  storeLogoUrl: string | null;
  itemCount: number;
  discountCount: number;
  onPress: () => void;
}

export function StoreCard({ storeName, storeLogoUrl, itemCount, discountCount, onPress }: StoreCardProps) {
  // The store now lists its whole browsed catalog, not just confirmed discounts (see
  // grocery_discounts.py) -- "X varer" (items) is the honest count; "Y på tilbud" is
  // called out separately only when we actually found real discounts among them.
  const subtitle = discountCount > 0 ? `${itemCount} varer · ${discountCount} på tilbud` : `${itemCount} varer`;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7} testID="store-card">
      {storeLogoUrl ? (
        <Image source={{ uri: storeLogoUrl }} style={styles.logo} resizeMode="contain" />
      ) : (
        <View style={[styles.logo, styles.logoPlaceholder]}>
          <Text style={styles.logoPlaceholderText}>🏬</Text>
        </View>
      )}
      <View style={styles.info}>
        <Text style={styles.storeName} numberOfLines={1}>
          {storeName}
        </Text>
        <Text style={styles.itemCount}>{subtitle}</Text>
      </View>
      <Text style={styles.chevron}>›</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 14,
    marginHorizontal: 16,
    marginBottom: 10,
    boxShadow: "0px 1px 3px rgba(0, 0, 0, 0.08)",
    elevation: 2,
  },
  logo: { width: 44, height: 44, borderRadius: 8, marginRight: 12, backgroundColor: "#f5f5f5" },
  logoPlaceholder: { alignItems: "center", justifyContent: "center" },
  logoPlaceholderText: { fontSize: 20 },
  info: { flex: 1 },
  storeName: { fontSize: 16, fontWeight: "700", color: "#1a1a1a" },
  itemCount: { fontSize: 13, color: "#888", marginTop: 2 },
  chevron: { fontSize: 22, color: "#ccc", marginLeft: 8 },
});

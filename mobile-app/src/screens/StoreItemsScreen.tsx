import type { RouteProp } from "@react-navigation/native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { DealCard } from "../components/DealCard";
import type { TilbudStackParamList } from "../navigation/types";
import type { DiscountedProduct } from "../types/api";

// A missing/null category (an older cached row) falls into "Food", same fallback
// StoresScreen's Food/Non-food tab split uses -- never silently dropped.
const SECTIONS: { key: string; label: string; match: (d: DiscountedProduct) => boolean }[] = [
  { key: "main_food", label: "Food", match: (d) => (d.category ?? "main_food") === "main_food" },
  { key: "snack", label: "Snacks", match: (d) => d.category === "snack" },
  { key: "non_food", label: "Non-food", match: (d) => d.category === "non_food" },
];

export function StoreItemsScreen() {
  const route = useRoute<RouteProp<TilbudStackParamList, "StoreItems">>();
  const navigation = useNavigation<NativeStackNavigationProp<TilbudStackParamList, "StoreItems">>();
  const { store } = route.params;

  const sections = SECTIONS.map((section) => ({ ...section, deals: store.deals.filter(section.match) })).filter(
    (section) => section.deals.length > 0
  );
  // Only label sections when this store's items actually mix categories (the Food
  // tab's main_food + snack) -- a single-category store (every Non-food-tab store,
  // or a Food-tab store with no snacks at all) just shows its grid with no
  // redundant lone header.
  const showHeaders = sections.length > 1;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent} testID="store-items-screen">
      {sections.map((section) => (
        <View key={section.key}>
          {showHeaders ? <Text style={styles.sectionHeader}>{section.label}</Text> : null}
          <View style={styles.grid}>
            {section.deals.map((deal, index) => (
              <View key={`${deal.product_name}-${index}`} style={styles.cell}>
                <DealCard deal={deal} onPress={() => navigation.navigate("DealDetail", { deal })} />
              </View>
            ))}
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  scrollContent: { padding: 12, paddingBottom: 24 },
  sectionHeader: { fontSize: 18, fontWeight: "700", color: "#1a1a1a", marginTop: 12, marginBottom: 8 },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  cell: { width: "48%", marginBottom: 12 },
});

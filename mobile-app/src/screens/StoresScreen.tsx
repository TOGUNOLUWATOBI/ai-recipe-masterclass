import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getDiscountedRecipes } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { LanguageToggle } from "../components/LanguageToggle";
import { StoreCard } from "../components/StoreCard";
import { useLanguage } from "../i18n/LanguageContext";
import type { StoreGroup, TilbudStackParamList } from "../navigation/types";
import type { DiscountedProduct, DiscountedResponse } from "../types/api";

// Exported so other screens that reuse groupByStore() (e.g. MealIdeaStoreSelectionScreen)
// can tell a real store name apart from this display-only placeholder -- it must never
// be sent to the backend as an actual store_name filter value (see that screen's own
// translation back to the "unknown-store" convention meal_ideas.py's
// resolve_store_items()/_discount_item_id() already use for the same null case).
export const FALLBACK_STORE_LABEL = "Other deals";

// "Food" covers both main_food and snack -- snacks are still food, just not something
// recipe generation uses (see grocery_discounts.classify_product() on the backend). A
// missing/null category (an older cached row from before this field existed) defaults
// to the Food tab rather than disappearing into Non-food.
type DealsTab = "food" | "non_food";

export function matchesTab(deal: DiscountedProduct, tab: DealsTab): boolean {
  const category = deal.category ?? "main_food";
  return tab === "non_food" ? category === "non_food" : category !== "non_food";
}

export function groupByStore(deals: DiscountedProduct[]): StoreGroup[] {
  const groups = new Map<string, StoreGroup>();
  for (const deal of deals) {
    const key = deal.store_name ?? FALLBACK_STORE_LABEL;
    const existing = groups.get(key);
    if (existing) {
      existing.deals.push(deal);
    } else {
      groups.set(key, { storeName: key, storeLogoUrl: deal.store_logo_url, deals: [deal] });
    }
  }
  return Array.from(groups.values());
}

function formatUpdatedAt(iso: string | null, t: ReturnType<typeof useLanguage>["t"]): string {
  if (!iso) return "";
  const date = new Date(iso);
  const datePart = date.toLocaleDateString("nb-NO");
  const timePart = date.toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
  return t.storesUpdatedAt(datePart, timePart);
}

export function StoresScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<TilbudStackParamList, "StoresList">>();
  const insets = useSafeAreaInsets();
  const { t } = useLanguage();
  const [loading, setLoading] = useState(true);
  const [response, setResponse] = useState<DiscountedResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [tab, setTab] = useState<DealsTab>("food");

  const load = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const result = await getDiscountedRecipes(20, false);
      if (result.error) {
        setErrorMessage(result.error);
      } else {
        setResponse(result);
      }
    } catch (err) {
      setErrorMessage(userMessageForError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !response) {
    return (
      <View style={styles.centered} testID="stores-loading">
        <ActivityIndicator size="large" color="#e63946" />
      </View>
    );
  }

  const tabDeals = response ? response.discounted_ingredients.filter((d) => matchesTab(d, tab)) : [];
  const groups = groupByStore(tabDeals);

  return (
    <View style={styles.container}>
      <View style={[styles.headerRow, { paddingTop: insets.top + 16 }]}>
        <View style={styles.headerTopRow}>
          <Text style={styles.heading}>{t.tabDeals}</Text>
          <LanguageToggle />
        </View>
        {response?.updated_at ? <Text style={styles.updatedAt}>{formatUpdatedAt(response.updated_at, t)}</Text> : null}
      </View>

      <View style={styles.tabRow}>
        <TouchableOpacity
          style={[styles.tabButton, tab === "food" && styles.tabButtonActive]}
          onPress={() => setTab("food")}
          testID="food-tab-button"
        >
          <Text style={[styles.tabButtonText, tab === "food" && styles.tabButtonTextActive]}>{t.foodTab}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tabButton, tab === "non_food" && styles.tabButtonActive]}
          onPress={() => setTab("non_food")}
          testID="non-food-tab-button"
        >
          <Text style={[styles.tabButtonText, tab === "non_food" && styles.tabButtonTextActive]}>{t.nonFoodTab}</Text>
        </TouchableOpacity>
      </View>

      {errorMessage ? (
        <View style={styles.errorWrap}>
          <ErrorBanner message={errorMessage} />
        </View>
      ) : null}

      <ScrollView
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} testID="stores-refresh-control" />}
        contentContainerStyle={styles.scrollContent}
      >
        {!loading && groups.length === 0 && !errorMessage ? (
          <Text style={styles.emptyText}>
            {tab === "non_food" ? t.storesEmptyNonFood : t.storesEmptyFood}
          </Text>
        ) : (
          groups.map((group) => (
            <StoreCard
              key={group.storeName}
              storeName={group.storeName}
              storeLogoUrl={group.storeLogoUrl}
              itemCount={group.deals.length}
              discountCount={group.deals.filter((d) => d.discount_pct != null && d.reference_price != null).length}
              onPress={() => navigation.navigate("StoreItems", { store: group })}
            />
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f5f5f5" },
  headerRow: { paddingHorizontal: 16, paddingBottom: 8 },
  headerTopRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  heading: { fontSize: 26, fontWeight: "800", color: "#1a1a1a" },
  updatedAt: { fontSize: 12, color: "#888", marginTop: 2 },
  tabRow: {
    flexDirection: "row",
    marginHorizontal: 16,
    marginBottom: 12,
    backgroundColor: "#eee",
    borderRadius: 10,
    padding: 3,
  },
  tabButton: { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: "center" },
  tabButtonActive: { backgroundColor: "#fff", boxShadow: "0px 1px 2px rgba(0, 0, 0, 0.1)" },
  tabButtonText: { fontSize: 14, fontWeight: "600", color: "#888" },
  tabButtonTextActive: { color: "#1a1a1a" },
  errorWrap: { paddingHorizontal: 16, marginBottom: 4 },
  scrollContent: { paddingBottom: 24 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#666", fontSize: 14, paddingHorizontal: 16 },
});

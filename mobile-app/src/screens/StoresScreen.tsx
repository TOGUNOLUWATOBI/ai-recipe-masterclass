import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { getDiscountedRecipes } from "../api/client";
import { userMessageForError } from "../api/errors";
import { ErrorBanner } from "../components/ErrorBanner";
import { StoreCard } from "../components/StoreCard";
import type { StoreGroup, TilbudStackParamList } from "../navigation/types";
import type { DiscountedProduct, DiscountedResponse } from "../types/api";

const FALLBACK_STORE_LABEL = "Andre tilbud";

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

function formatUpdatedAt(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const datePart = date.toLocaleDateString("nb-NO");
  const timePart = date.toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
  return `Oppdatert ${datePart} ${timePart}`;
}

export function StoresScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<TilbudStackParamList, "StoresList">>();
  const [loading, setLoading] = useState(true);
  const [response, setResponse] = useState<DiscountedResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  const groups = response ? groupByStore(response.discounted_ingredients) : [];

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Tilbud</Text>
        {response?.updated_at ? <Text style={styles.updatedAt}>{formatUpdatedAt(response.updated_at)}</Text> : null}
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
          <Text style={styles.emptyText}>Ingen varer funnet akkurat nå — sjekk igjen senere.</Text>
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
  headerRow: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8 },
  heading: { fontSize: 26, fontWeight: "800", color: "#1a1a1a" },
  updatedAt: { fontSize: 12, color: "#888", marginTop: 2 },
  errorWrap: { paddingHorizontal: 16, marginBottom: 4 },
  scrollContent: { paddingBottom: 24 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#666", fontSize: 14, paddingHorizontal: 16 },
});

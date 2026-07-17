import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCart } from "../cart/CartContext";
import { LanguageToggle } from "../components/LanguageToggle";
import { useLanguage } from "../i18n/LanguageContext";
import type { MealIdeasStackParamList } from "../navigation/types";

// Epic E1: two clear starting points -- "From my cart" (Epic C's existing selection,
// see CartContext's selected_for_meal_ideas) or "From a store's offers" (Epic E2) --
// replacing the old free-text Ingredients search entirely (see the epic's acceptance
// criteria: this tab is Meal Ideas now, not a second recipe-search box).
export function MealIdeasScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<MealIdeasStackParamList, "MealIdeasHome">>();
  const insets = useSafeAreaInsets();
  const { t } = useLanguage();
  const { mealIdeaSelectedCount } = useCart();

  return (
    <View style={[styles.container, { paddingTop: insets.top + 16 }]} testID="meal-ideas-home">
      <View style={styles.headerRow}>
        <Text style={styles.heading}>{t.mealIdeasEntryHeading}</Text>
        <LanguageToggle />
      </View>

      <TouchableOpacity
        style={styles.card}
        onPress={() => navigation.navigate("MealIdeasResults", { source: "cart" })}
        testID="meal-ideas-from-cart-entry"
      >
        <Ionicons name="cart" size={28} color="#e63946" />
        <View style={styles.cardTextWrap}>
          <Text style={styles.cardTitle}>{t.mealIdeasFromCartTitle}</Text>
          <Text style={styles.cardSubtitle}>{t.mealIdeasFromCartSubtitle(mealIdeaSelectedCount)}</Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color="#ccc" />
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.card}
        onPress={() => navigation.navigate("MealIdeasStoreSelection")}
        testID="meal-ideas-from-store-entry"
      >
        <Ionicons name="pricetags" size={28} color="#e63946" />
        <View style={styles.cardTextWrap}>
          <Text style={styles.cardTitle}>{t.mealIdeasFromStoreTitle}</Text>
          <Text style={styles.cardSubtitle}>{t.mealIdeasFromStoreSubtitle}</Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color="#ccc" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", paddingHorizontal: 16 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 20 },
  heading: { fontSize: 26, fontWeight: "800", color: "#1a1a1a" },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  cardTextWrap: { flex: 1, gap: 2 },
  cardTitle: { fontSize: 16, fontWeight: "700", color: "#1a1a1a" },
  cardSubtitle: { fontSize: 13, color: "#888" },
});

import React from "react";
import { StyleSheet, View } from "react-native";
import { Text } from "./AppText";
import { useLanguage } from "../i18n/LanguageContext";
import { parseRecipeText } from "../utils/parseRecipeText";

interface RecipeCardProps {
  title?: string | null;
  text: string;
  meta?: string | null;
}

export function RecipeCard({ title, text, meta }: RecipeCardProps) {
  const { t } = useLanguage();
  const parsed = parseRecipeText(text);
  const displayTitle = title || parsed.title || "Recipe";
  const hasStructuredContent = Boolean(parsed.ingredients || parsed.instructions);

  return (
    <View style={styles.card} testID="recipe-card">
      <Text style={styles.title}>{displayTitle}</Text>
      {meta ? <Text style={styles.meta}>{meta}</Text> : null}

      {hasStructuredContent ? (
        <>
          {parsed.ingredients ? (
            <View style={styles.section}>
              <Text style={styles.sectionHeader}>{t.recipeIngredientsLabel}</Text>
              <Text style={styles.body}>{parsed.ingredients}</Text>
            </View>
          ) : null}
          {parsed.instructions ? (
            <View style={styles.section}>
              <Text style={styles.sectionHeader}>{t.recipeInstructionsLabel}</Text>
              <Text style={styles.body}>{parsed.instructions}</Text>
            </View>
          ) : null}
        </>
      ) : (
        <Text style={styles.body}>{text}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 16,
    marginVertical: 8,
    boxShadow: "0px 1px 3px rgba(0, 0, 0, 0.08)",
    elevation: 2,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 4,
    color: "#1a1a1a",
  },
  meta: {
    fontSize: 12,
    color: "#888",
    marginBottom: 8,
  },
  section: {
    marginTop: 8,
  },
  sectionHeader: {
    fontSize: 14,
    fontWeight: "600",
    color: "#c0392b",
    marginBottom: 2,
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
    color: "#333",
  },
});

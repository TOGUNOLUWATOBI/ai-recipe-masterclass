import React from "react";
import { StyleSheet, Text, View } from "react-native";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <View style={styles.banner} testID="error-banner">
      <Text style={styles.text}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: "#fdecea",
    borderRadius: 8,
    padding: 12,
    marginVertical: 8,
  },
  text: {
    color: "#c0392b",
    fontSize: 14,
  },
});

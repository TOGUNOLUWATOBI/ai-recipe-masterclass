import type { RouteProp } from "@react-navigation/native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { DealCard } from "../components/DealCard";
import type { TilbudStackParamList } from "../navigation/types";

export function StoreItemsScreen() {
  const route = useRoute<RouteProp<TilbudStackParamList, "StoreItems">>();
  const navigation = useNavigation<NativeStackNavigationProp<TilbudStackParamList, "StoreItems">>();
  const { store } = route.params;

  return (
    <View style={styles.container} testID="store-items-screen">
      <FlatList
        data={store.deals}
        keyExtractor={(item, index) => `${item.product_name}-${index}`}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={styles.cell}>
            <DealCard deal={item} onPress={() => navigation.navigate("DealDetail", { deal: item })} />
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  list: { padding: 12 },
  row: { gap: 8 },
  cell: { flex: 1, marginBottom: 8 },
});

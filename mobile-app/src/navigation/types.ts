import type { DiscountedProduct } from "../types/api";

export interface StoreGroup {
  storeName: string;
  storeLogoUrl: string | null;
  deals: DiscountedProduct[];
}

export type TilbudStackParamList = {
  StoresList: undefined;
  StoreItems: { store: StoreGroup };
  DealDetail: { deal: DiscountedProduct };
};

// Epic E: "From my cart" needs no params (reads the current cart directly); "From a
// store's offers" first lets the user pick a store, then lands on the same results
// screen with a different source.
export type MealIdeasResultsParams =
  | { source: "cart" }
  | { source: "store"; storeName: string };

export type MealIdeasStackParamList = {
  MealIdeasHome: undefined;
  MealIdeasStoreSelection: undefined;
  MealIdeasResults: MealIdeasResultsParams;
};

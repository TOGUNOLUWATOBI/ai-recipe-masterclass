import type { DiscountedProduct } from "../types/api";

// The bottom tab navigator's own route names -- used by HomeScreen to jump straight to
// another tab (e.g. the Dagens Deals shortcut) rather than nesting through that tab's
// own internal stack params, which HomeScreen has no reason to know about.
export type RootTabParamList = {
  Home: undefined;
  Tilbud: undefined;
  Cart: undefined;
  Ask: undefined;
  MealIdeas: undefined;
};

export type HomeStackParamList = {
  HomeMain: undefined;
  Login: undefined;
  VerifyOtp: { phone: string };
  PrivacyPolicy: undefined;
};

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

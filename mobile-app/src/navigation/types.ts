import type { DiscountedProduct } from "../types/api";

// The root-level stack: either the pre-consent Terms gate or the main tab experience is
// mounted as "the" screen here (see AppNavigator.tsx's hasAcceptedTerms conditional) --
// TermsAndConditions/PrivacyPolicy stay in this same stack regardless of which one is
// active, so both the gate and the Settings tab (nested inside MainTabs) can reach them
// via a plain navigate() call that bubbles up to this root.
export type RootStackParamList = {
  TermsGate: undefined;
  MainTabs: undefined;
  TermsAndConditions: undefined;
  PrivacyPolicy: undefined;
};

// The bottom tab navigator's own route names.
export type RootTabParamList = {
  Tilbud: undefined;
  Cart: undefined;
  Ask: undefined;
  MealIdeas: undefined;
  Settings: undefined;
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

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

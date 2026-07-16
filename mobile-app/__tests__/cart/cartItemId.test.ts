import { cartItemIdFor } from "../../src/types/cart";

describe("cartItemIdFor", () => {
  it("combines store name and product name", () => {
    expect(cartItemIdFor({ product_name: "Kyllingfilet", store_name: "Kiwi" })).toBe("Kiwi::Kyllingfilet");
  });

  it("falls back to a placeholder store label when store_name is null", () => {
    expect(cartItemIdFor({ product_name: "Kyllingfilet", store_name: null })).toBe("unknown-store::Kyllingfilet");
  });

  it("produces the same id for the same (store, product) pair, enabling dedup", () => {
    const a = cartItemIdFor({ product_name: "Laksefilet", store_name: "Meny" });
    const b = cartItemIdFor({ product_name: "Laksefilet", store_name: "Meny" });
    expect(a).toBe(b);
  });

  it("produces different ids for the same product from different stores", () => {
    const a = cartItemIdFor({ product_name: "Laksefilet", store_name: "Meny" });
    const b = cartItemIdFor({ product_name: "Laksefilet", store_name: "Kiwi" });
    expect(a).not.toBe(b);
  });
});

import { screen, userEvent } from "@testing-library/react-native";
import React from "react";
import { StoreCard } from "../../src/components/StoreCard";
import { renderWithProviders } from "../../test-utils/testUtils";

describe("StoreCard", () => {
  it("shows the item count alone when nothing in the store is discounted", async () => {
    await renderWithProviders(<StoreCard storeName="Coop" storeLogoUrl={null} itemCount={87} discountCount={0} onPress={() => {}} />);

    expect(screen.getByText("Coop")).toBeTruthy();
    expect(screen.getByText("87 items")).toBeTruthy();
  });

  it("calls out the discount count separately when some items are discounted", async () => {
    await renderWithProviders(<StoreCard storeName="Coop" storeLogoUrl={null} itemCount={87} discountCount={12} onPress={() => {}} />);

    expect(screen.getByText("87 items · 12 on sale")).toBeTruthy();
  });

  it("shows a placeholder icon when there is no store logo", async () => {
    await renderWithProviders(<StoreCard storeName="Coop" storeLogoUrl={null} itemCount={1} discountCount={0} onPress={() => {}} />);

    expect(screen.getByText("🏬")).toBeTruthy();
  });

  it("calls onPress when tapped", async () => {
    const onPress = jest.fn();
    const user = userEvent.setup();
    await renderWithProviders(<StoreCard storeName="Coop" storeLogoUrl={null} itemCount={1} discountCount={0} onPress={onPress} />);

    await user.press(screen.getByTestId("store-card"));

    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

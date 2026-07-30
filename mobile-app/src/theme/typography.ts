/**
 * Inter (SIL Open Font License, see assets/fonts/LICENSE_Inter.txt), bundled as local
 * font files rather than the @expo-google-fonts/inter npm package -- same two static
 * weights that package would provide, without adding a dependency. Loaded once via
 * useFonts() in App.tsx; every screen should get this applied automatically through
 * components/AppText.tsx rather than setting fontFamily itself.
 */
export const FONT_REGULAR = "Inter_400Regular";
export const FONT_BOLD = "Inter_700Bold";

export const FONT_ASSETS = {
  Inter_400Regular: require("../../assets/fonts/Inter_400Regular.ttf"),
  Inter_700Bold: require("../../assets/fonts/Inter_700Bold.ttf"),
};

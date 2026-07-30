import React from "react";
import { Text as RNText, type TextProps } from "react-native";
import { FONT_REGULAR } from "../theme/typography";

/**
 * Drop-in replacement for react-native's own Text -- every screen imports Text from
 * here instead, so the bundled Inter font applies everywhere without each screen's
 * StyleSheet needing its own fontFamily line. React Native's own docs recommend
 * exactly this wrapper-component pattern for an app-wide default font (Text.defaultProps
 * is explicitly called out there as unreliable, not what to use).
 *
 * A caller's own `style` can still override fontFamily (e.g. for the bold weight, see
 * theme/typography.ts's FONT_BOLD) -- the default is applied first in the style array,
 * so anything more specific in the caller's style still wins.
 */
export function Text({ style, ...props }: TextProps) {
  return <RNText style={[{ fontFamily: FONT_REGULAR }, style]} {...props} />;
}

import React from "react";
import { TextInput as RNTextInput, type TextInputProps } from "react-native";
import { FONT_REGULAR } from "../theme/typography";

/** Same purpose as AppText.tsx, for TextInput -- see that file's comment. */
export function TextInput({ style, ...props }: TextInputProps) {
  return <RNTextInput style={[{ fontFamily: FONT_REGULAR }, style]} {...props} />;
}

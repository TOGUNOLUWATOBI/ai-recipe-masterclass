/**
 * Plain module-level current-language state, kept in sync by LanguageContext's
 * provider. Exists alongside the React Context (not instead of it) specifically for
 * api/errors.ts and api/validation.ts -- plain TS modules outside the component tree
 * that can't call a React hook, but still need to know which language to render a
 * message in. Components should use useLanguage() from LanguageContext.tsx, not this
 * file directly.
 */

export type Language = "en" | "no";

export const DEFAULT_LANGUAGE: Language = "en";

let currentLanguage: Language = DEFAULT_LANGUAGE;
type Listener = (language: Language) => void;
const listeners = new Set<Listener>();

export function getLanguage(): Language {
  return currentLanguage;
}

export function setLanguage(language: Language): void {
  currentLanguage = language;
  listeners.forEach((listener) => listener(language));
}

export function subscribeToLanguage(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

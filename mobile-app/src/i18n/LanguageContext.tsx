import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { DEFAULT_LANGUAGE, Language, setLanguage as setSharedLanguage } from "./language";
import { translations } from "./translations";

const STORAGE_KEY = "language";

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (typeof translations)[Language];
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>(DEFAULT_LANGUAGE);

  // Loads the persisted choice once on mount -- a fresh install (or a read failure)
  // just keeps the DEFAULT_LANGUAGE this component already started with.
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (stored === "en" || stored === "no") {
          setLanguageState(stored);
          setSharedLanguage(stored);
        }
      })
      .catch(() => {
        // Ignore -- falls back to DEFAULT_LANGUAGE, same as a fresh install.
      });
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    setSharedLanguage(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {
      // Best-effort persistence -- the toggle still works for the rest of this
      // session even if storage write fails, it just won't survive an app restart.
    });
  }, []);

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t: translations[language] }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage() must be called within a LanguageProvider");
  }
  return context;
}

import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "has_accepted_terms";

interface ConsentContextValue {
  // false until the persisted flag has been read once on mount -- lets AppNavigator
  // avoid flashing the Terms gate for a split second on every cold launch before a
  // previous "I Agree" has had a chance to load back in, same isHydrated guard
  // CartContext already uses for the exact same reason.
  isHydrated: boolean;
  hasAcceptedTerms: boolean;
  acceptTerms: () => void;
}

const ConsentContext = createContext<ConsentContextValue | null>(null);

export function ConsentProvider({ children }: { children: React.ReactNode }) {
  const [hasAcceptedTerms, setHasAcceptedTerms] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const hasHydrated = useRef(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (stored === "true") setHasAcceptedTerms(true);
      })
      .catch(() => {
        // Ignore -- falls back to not-yet-accepted, same as a fresh install.
      })
      .finally(() => {
        hasHydrated.current = true;
        setIsHydrated(true);
      });
  }, []);

  const acceptTerms = useCallback(() => {
    setHasAcceptedTerms(true);
    AsyncStorage.setItem(STORAGE_KEY, "true").catch(() => {
      // Best-effort persistence -- the user still gets into the app for the rest of
      // this session even if the write fails, it just won't survive an app restart
      // (they'd see the Terms gate again next launch, same as never having accepted).
    });
  }, []);

  return (
    <ConsentContext.Provider value={{ isHydrated, hasAcceptedTerms, acceptTerms }}>{children}</ConsentContext.Provider>
  );
}

export function useConsent(): ConsentContextValue {
  const context = useContext(ConsentContext);
  if (!context) {
    throw new Error("useConsent must be used within a ConsentProvider");
  }
  return context;
}

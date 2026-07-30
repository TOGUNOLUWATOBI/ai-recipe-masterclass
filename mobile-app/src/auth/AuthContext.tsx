import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { sendPhoneOtp, verifyPhoneOtp, type SupabaseSession } from "../api/supabaseAuth";

const STORAGE_KEY = "auth_session";

interface StoredSession extends SupabaseSession {
  phone: string;
}

interface AuthContextValue {
  // null until the persisted session has been read once on mount -- lets callers
  // distinguish "still checking" from "confirmed logged out", the same isHydrated
  // guard CartContext uses, just exposed to consumers here since the login screen
  // needs to know when it's safe to redirect a returning user.
  isHydrated: boolean;
  phone: string | null;
  isLoggedIn: boolean;
  sendCode: (phone: string) => Promise<void>;
  verifyCode: (phone: string, code: string) => Promise<void>;
  logOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<StoredSession | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);
  const hasHydrated = useRef(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (!stored) return;
        try {
          const parsed = JSON.parse(stored);
          if (parsed && typeof parsed.phone === "string" && typeof parsed.access_token === "string") {
            setSession(parsed);
          }
        } catch {
          // Corrupt persisted value -- ignore, stays logged out.
        }
      })
      .catch(() => {
        // Ignore -- falls back to logged out, same as a fresh install.
      })
      .finally(() => {
        hasHydrated.current = true;
        setIsHydrated(true);
      });
  }, []);

  useEffect(() => {
    if (!hasHydrated.current) return;
    const write = session ? AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(session)) : AsyncStorage.removeItem(STORAGE_KEY);
    write.catch(() => {
      // Best-effort persistence -- login still works for the rest of this session
      // even if the write fails, it just won't survive an app restart.
    });
  }, [session]);

  const sendCode = useCallback(async (phone: string) => {
    await sendPhoneOtp(phone);
  }, []);

  const verifyCode = useCallback(async (phone: string, code: string) => {
    const supabaseSession = await verifyPhoneOtp(phone, code);
    setSession({ ...supabaseSession, phone });
  }, []);

  const logOut = useCallback(async () => {
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ isHydrated, phone: session?.phone ?? null, isLoggedIn: session !== null, sendCode, verifyCode, logOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

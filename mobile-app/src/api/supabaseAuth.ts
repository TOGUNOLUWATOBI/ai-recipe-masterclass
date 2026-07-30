import { SUPABASE_ANON_KEY, SUPABASE_URL } from "../config";
import { ApiError } from "./errors";

/**
 * Plain-fetch client for Supabase Auth's phone-OTP REST endpoints -- deliberately not
 * the @supabase/supabase-js SDK, to match this app's existing convention (see
 * api/client.ts) of talking to a backend directly via fetch rather than adding a
 * client SDK dependency. The REST contract itself (POST /auth/v1/otp to send a code,
 * POST /auth/v1/verify to redeem it) is small and stable enough that this is a better
 * fit here than a whole SDK.
 */

const AUTH_TIMEOUT_MS = 15_000;

export interface SupabaseSession {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

async function supabaseFetch<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), AUTH_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${SUPABASE_URL}${path}`, {
      method: "POST",
      signal: controller.signal,
      headers: { "Content-Type": "application/json", apikey: SUPABASE_ANON_KEY },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError("timeout", "Request timed out");
    }
    throw new ApiError("network", err instanceof Error ? err.message : "Network request failed");
  } finally {
    clearTimeout(timeout);
  }

  let json: unknown;
  try {
    json = await response.json();
  } catch {
    json = null;
  }

  if (!response.ok) {
    // Supabase's own error responses carry a human-readable "msg" or "error_description".
    const message =
      (json as { msg?: string; error_description?: string } | null)?.msg ??
      (json as { msg?: string; error_description?: string } | null)?.error_description ??
      `Request failed with status ${response.status}`;
    throw new ApiError("backend", message, response.status);
  }

  return json as T;
}

/** Sends a 6-digit SMS code to `phone` (E.164 format, e.g. "+4791234567"). */
export async function sendPhoneOtp(phone: string): Promise<void> {
  await supabaseFetch<Record<string, never>>("/auth/v1/otp", { phone });
}

/** Redeems the SMS code, returning a session on success. */
export async function verifyPhoneOtp(phone: string, token: string): Promise<SupabaseSession> {
  return supabaseFetch<SupabaseSession>("/auth/v1/verify", { type: "sms", phone, token });
}

/**
 * Single source of truth for the backend base URL. Deliberately not user-configurable
 * anywhere in the UI — a settings screen that lets users point the app at an arbitrary
 * host would let a malicious actor redirect all traffic (including whatever the app
 * sends) to a server they control. HTTPS-only; there is no HTTP fallback.
 */
export const API_BASE_URL = "https://recipe.bebs.dev";

// LLM-backed endpoints are slow by nature (multi-recipe generation can chain several
// sequential model calls) — timeouts below are generous on purpose. Confirmed live
// against production on 2026-07-09: a single-ingredient /recipes/from-ingredients call
// (max_results=5, cache miss) took ~97s end to end, well past the previous 60s timeout —
// that's what caused real "Request timed out" errors on-device even though the backend
// was still working and had already succeeded by the time it got re-queried.
export const DEFAULT_TIMEOUT_MS = 150_000; // /query, /recipes/from-ingredients
export const DISCOUNTED_TIMEOUT_MS = 180_000; // /recipes/discounted scans ~33 ingredients sequentially

// Phone-number login (Supabase Auth, phone OTP) -- placeholders until a real Supabase
// project exists. Replace both once you've created one: Project Settings -> API ->
// Project URL / anon public key. The anon key is safe to ship in client code by
// design (Supabase's Row Level Security policies are what actually gate access, not
// keeping this key secret) -- same "no secrets in this file" posture as
// API_BASE_URL above, no .env needed.
export const SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"; // TODO: replace once the Supabase project exists
export const SUPABASE_ANON_KEY = "YOUR-ANON-KEY"; // TODO: replace once the Supabase project exists

/**
 * Single source of truth for the backend base URL. Deliberately not user-configurable
 * anywhere in the UI — a settings screen that lets users point the app at an arbitrary
 * host would let a malicious actor redirect all traffic (including whatever the app
 * sends) to a server they control. HTTPS-only; there is no HTTP fallback.
 */
// TEMPORARY — local Docker test of the store-sweep redesign, pending macmini SSH access.
// MUST be switched back to "https://recipe.bebs.dev" before this app is used for real.
export const API_BASE_URL = "http://192.168.68.104:8011";

// LLM-backed endpoints are slow by nature (multi-recipe generation can chain several
// sequential model calls) — timeouts below are generous on purpose, sized from actual
// observed latency during backend testing, not guessed.
export const DEFAULT_TIMEOUT_MS = 60_000; // /query, /recipes/from-ingredients
export const DISCOUNTED_TIMEOUT_MS = 180_000; // /recipes/discounted scans ~33 ingredients sequentially

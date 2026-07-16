import { getLanguage } from "../i18n/language";
import { translations } from "../i18n/translations";

/**
 * Distinguishing error kinds matters for the UI: a timeout ("the model is slow, try
 * again") reads very differently to a user than a network-down error ("check your
 * connection") or a backend-reported failure ("something went wrong server-side").
 * Collapsing these into one generic "Error" would make every failure equally
 * confusing.
 */
export type ApiErrorKind = "network" | "timeout" | "http" | "backend" | "invalid_response";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly statusCode?: number;

  constructor(kind: ApiErrorKind, message: string, statusCode?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.statusCode = statusCode;
  }
}

// error.message on the "backend" branch is the server's own text, which is always
// English (see translations.ts's module docstring on why backend-generated content
// stays untranslated) -- only the OTHER branches here (this app's own copy) respect
// the selected language, via the plain (non-hook) language singleton, since this
// module sits outside the component tree and can't call useLanguage().
export function userMessageForError(error: unknown): string {
  const t = translations[getLanguage()];
  if (error instanceof ApiError) {
    switch (error.kind) {
      case "network":
        return t.errorNetwork;
      case "timeout":
        return t.errorTimeout;
      case "http":
        return t.errorHttp(error.statusCode ?? "unknown");
      case "backend":
        return error.message || t.errorBackendFallback;
      case "invalid_response":
        return t.errorInvalidResponse;
      default:
        return t.errorGeneric;
    }
  }
  return t.errorGeneric;
}

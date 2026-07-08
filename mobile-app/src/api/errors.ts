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

export function userMessageForError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case "network":
        return "Can't reach the server. Check your internet connection and try again.";
      case "timeout":
        return "That took too long to respond. Please try again.";
      case "http":
        return `Server error (${error.statusCode ?? "unknown"}). Please try again later.`;
      case "backend":
        return error.message || "Something went wrong generating a response.";
      case "invalid_response":
        return "Got an unexpected response from the server. Please try again.";
      default:
        return "Something went wrong.";
    }
  }
  return "Something went wrong.";
}

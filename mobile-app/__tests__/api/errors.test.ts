import { ApiError, userMessageForError } from "../../src/api/errors";
import { DEFAULT_LANGUAGE, setLanguage } from "../../src/i18n/language";

describe("userMessageForError", () => {
  afterEach(() => {
    setLanguage(DEFAULT_LANGUAGE);
  });

  it("maps each ApiError kind to a distinct message", () => {
    expect(userMessageForError(new ApiError("network", "x"))).toMatch(/internet connection/i);
    expect(userMessageForError(new ApiError("timeout", "x"))).toMatch(/took too long/i);
    expect(userMessageForError(new ApiError("http", "x", 500))).toBe("Server error (500). Please try again later.");
    expect(userMessageForError(new ApiError("invalid_response", "x"))).toMatch(/unexpected response/i);
  });

  it("uses the server's own message for a backend error when present", () => {
    expect(userMessageForError(new ApiError("backend", "Generation failed: model timeout"))).toBe(
      "Generation failed: model timeout"
    );
  });

  it("falls back to a generic backend message when the server sent no message", () => {
    expect(userMessageForError(new ApiError("backend", ""))).toBe("Something went wrong generating a response.");
  });

  it("falls back to a generic message for a non-ApiError", () => {
    expect(userMessageForError(new Error("some other failure"))).toBe("Something went wrong.");
    expect(userMessageForError("not even an Error instance")).toBe("Something went wrong.");
  });

  it("uses an 'unknown' placeholder when an http error has no status code", () => {
    expect(userMessageForError(new ApiError("http", "x"))).toBe("Server error (unknown). Please try again later.");
  });

  it("switches to Norwegian messages when the app language is Norwegian", () => {
    setLanguage("no");

    expect(userMessageForError(new ApiError("network", "x"))).toBe(
      "Får ikke kontakt med serveren. Sjekk internettforbindelsen og prøv igjen."
    );
    expect(userMessageForError(new Error("x"))).toBe("Noe gikk galt.");
  });

  it("never translates the server's own backend error message, regardless of app language", () => {
    setLanguage("no");

    expect(userMessageForError(new ApiError("backend", "Generation failed: model timeout"))).toBe(
      "Generation failed: model timeout"
    );
  });
});

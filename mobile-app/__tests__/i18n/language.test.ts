import { DEFAULT_LANGUAGE, getLanguage, setLanguage, subscribeToLanguage } from "../../src/i18n/language";

describe("language singleton", () => {
  afterEach(() => {
    setLanguage(DEFAULT_LANGUAGE);
  });

  it("defaults to English", () => {
    expect(getLanguage()).toBe("en");
  });

  it("setLanguage updates what getLanguage returns", () => {
    setLanguage("no");
    expect(getLanguage()).toBe("no");
  });

  it("notifies subscribers when the language changes", () => {
    const listener = jest.fn();
    const unsubscribe = subscribeToLanguage(listener);

    setLanguage("no");

    expect(listener).toHaveBeenCalledWith("no");
    unsubscribe();
  });

  it("stops notifying a listener after it unsubscribes", () => {
    const listener = jest.fn();
    const unsubscribe = subscribeToLanguage(listener);
    unsubscribe();

    setLanguage("no");

    expect(listener).not.toHaveBeenCalled();
  });
});

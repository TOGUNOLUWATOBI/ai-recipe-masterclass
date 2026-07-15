import { act, screen, userEvent, waitFor, within } from "@testing-library/react-native";
import React from "react";
import { askQuestion } from "../../src/api/client";
import { ApiError } from "../../src/api/errors";
import { AskScreen } from "../../src/screens/AskScreen";
import { renderWithProviders } from "../../test-utils/testUtils";

jest.mock("../../src/api/client");

const mockedAskQuestion = askQuestion as jest.MockedFunction<typeof askQuestion>;

describe("AskScreen", () => {
  beforeEach(() => {
    mockedAskQuestion.mockReset();
  });

  it("renders the input and submit button", async () => {
    await renderWithProviders(<AskScreen />);
    expect(screen.getByTestId("ask-input")).toBeTruthy();
    expect(screen.getByTestId("ask-submit")).toBeTruthy();
  });

  it("submits the typed question and displays the answer", async () => {
    mockedAskQuestion.mockResolvedValueOnce({
      question: "norwegian ribbe",
      retrieved: [],
      grounded: [{ id: 1, score: 0.9, payload: { title: "Ribbe" }, text: "..." }],
      context: "...",
      answer: "### Ribbe\n\n**Ingredients:**\npork belly\n\n**Instructions:**\nRoast it.",
      error: null,
      elapsed: 2.1,
    });

    const user = userEvent.setup();
    await renderWithProviders(<AskScreen />);
    await user.type(screen.getByTestId("ask-input"), "norwegian ribbe");
    await user.press(screen.getByTestId("ask-submit"));

    await waitFor(() => expect(mockedAskQuestion).toHaveBeenCalledWith("norwegian ribbe"));
    const card = await screen.findByTestId("recipe-card");
    expect(within(card).getByText("Ribbe")).toBeTruthy();
    expect(screen.getByText(/Based on: Ribbe/)).toBeTruthy();
  });

  it("shows a note when nothing was grounded", async () => {
    mockedAskQuestion.mockResolvedValueOnce({
      question: "some obscure dish",
      retrieved: [],
      grounded: [],
      context: "(no matching reference recipe found)",
      answer: "### Best Guess Recipe",
      error: null,
      elapsed: 1.0,
    });

    const user = userEvent.setup();
    await renderWithProviders(<AskScreen />);
    await user.type(screen.getByTestId("ask-input"), "some obscure dish");
    await user.press(screen.getByTestId("ask-submit"));

    expect(await screen.findByText(/best-effort answer/i)).toBeTruthy();
  });

  it("shows an error banner when the API call fails", async () => {
    mockedAskQuestion.mockRejectedValueOnce(new ApiError("network", "no connection"));

    const user = userEvent.setup();
    await renderWithProviders(<AskScreen />);
    await user.type(screen.getByTestId("ask-input"), "test");
    await user.press(screen.getByTestId("ask-submit"));

    expect(await screen.findByTestId("error-banner")).toBeTruthy();
    expect(screen.getByText(/check your internet connection/i)).toBeTruthy();
  });

  it("shows an error banner when the backend reports an error field", async () => {
    mockedAskQuestion.mockResolvedValueOnce({
      question: "test",
      retrieved: [],
      grounded: [],
      context: "",
      answer: null,
      error: "Generation failed: model timeout",
      elapsed: 5.0,
    });

    const user = userEvent.setup();
    await renderWithProviders(<AskScreen />);
    await user.type(screen.getByTestId("ask-input"), "test");
    await user.press(screen.getByTestId("ask-submit"));

    expect(await screen.findByText("Generation failed: model timeout")).toBeTruthy();
  });

  it("does not fire a second request while one is already in flight", async () => {
    let resolveFirst: (value: any) => void = () => {};
    mockedAskQuestion.mockImplementationOnce(
      () => new Promise((resolve) => { resolveFirst = resolve; })
    );

    const user = userEvent.setup();
    await renderWithProviders(<AskScreen />);
    await user.type(screen.getByTestId("ask-input"), "test");
    await user.press(screen.getByTestId("ask-submit"));
    await user.press(screen.getByTestId("ask-submit")); // rapid second tap
    await user.press(screen.getByTestId("ask-submit")); // and a third

    expect(mockedAskQuestion).toHaveBeenCalledTimes(1);
    // Resolve the pending call so its state update is flushed inside act() — otherwise
    // React logs an "update not wrapped in act()" warning for a state change that
    // happens after the test's assertions but before the component unmounts.
    await act(async () => {
      resolveFirst({ question: "test", retrieved: [], grounded: [], context: "", answer: "ok", error: null, elapsed: 0.1 });
    });
  });
});

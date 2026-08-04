import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthStatus } from "@/components/HealthStatus";
import { TextReviewWorkspace } from "@/features/review/TextReviewWorkspace";
import { filterEntities, initialReviewState, reviewReducer } from "@/features/review/reviewState";
import * as api from "@/lib/api";
import HomePage from "@/app/page";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function setTextarea(label: RegExp, value: string) {
  const field = screen.getByLabelText(label) as HTMLTextAreaElement;
  fireEvent.change(field, { target: { value } });
}

describe("reviewReducer", () => {
  it("loads analysis and supports accept/reject filters", () => {
    let state = reviewReducer(initialReviewState, {
      type: "LOAD_ANALYSIS",
      text: "Email fictional.user@example.com phone 902-555-0182",
      detections: [
        {
          entity_type: "EMAIL_ADDRESS",
          start: 6,
          end: 32,
          text: "fictional.user@example.com",
          confidence: 0.95,
          detection_source: "regex",
          recognizer_name: "regex_email",
        },
        {
          entity_type: "PHONE_NUMBER",
          start: 39,
          end: 51,
          text: "902-555-0182",
          confidence: 0.5,
          detection_source: "regex",
          recognizer_name: "regex_canadian_phone",
        },
      ],
    });
    expect(state.entities).toHaveLength(2);
    const emailId = state.entities[0].id;
    state = reviewReducer(state, { type: "SET_STATUS", id: emailId, status: "rejected" });
    expect(state.entities[0].review_status).toBe("rejected");
    state = reviewReducer(state, {
      type: "SET_FILTERS",
      categoryFilter: "EMAIL_ADDRESS",
      confidenceThreshold: 0.9,
    });
    expect(filterEntities(state)).toHaveLength(1);
  });
});

describe("HealthStatus", () => {
  it("renders connected health state", async () => {
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      status: "ok",
      database: "connected",
      version: "0.1.0",
    });
    renderWithClient(<HealthStatus />);
    expect(await screen.findByText("All systems operational")).toBeInTheDocument();
  });
});

describe("HomePage", () => {
  it("renders workspace heading", () => {
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      status: "ok",
      database: "connected",
      version: "0.1.0",
    });
    renderWithClient(<HomePage />);
    expect(screen.getByRole("heading", { name: /^Workspace$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pasted text/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /document upload/i })).toBeInTheDocument();
  });
});

describe("TextReviewWorkspace", () => {
  it("analyzes, rejects one entity, anonymizes, and keeps rejected text", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "analyzeText").mockResolvedValue({
      text: "Email fictional.user@example.com and 902-555-0182",
      language: "en",
      detection_count: 2,
      entities: [
        {
          entity_type: "EMAIL_ADDRESS",
          start: 6,
          end: 32,
          text: "fictional.user@example.com",
          confidence: 0.95,
          detection_source: "regex",
          recognizer_name: "regex_email",
        },
        {
          entity_type: "PHONE_NUMBER",
          start: 37,
          end: 49,
          text: "902-555-0182",
          confidence: 0.88,
          detection_source: "regex",
          recognizer_name: "regex_canadian_phone",
        },
      ],
    });
    vi.spyOn(api, "anonymizeText").mockResolvedValue({
      anonymized_text: "Email <EMAIL_ADDRESS> and 902-555-0182",
      transformed_count: 1,
      rejected_count: 1,
      skipped_count: 0,
      method_counts: { replacement: 1 },
      warnings: [],
    });

    render(<TextReviewWorkspace />);
    await setTextarea(/Text to analyze/i, "Email fictional.user@example.com and 902-555-0182");
    await user.click(screen.getByRole("button", { name: /^Analyze text$/i }));

    expect(await screen.findByText(/Detections \(/i)).toBeInTheDocument();
    expect(screen.getAllByText("EMAIL_ADDRESS").length).toBeGreaterThan(0);
    expect(screen.getAllByText("PHONE_NUMBER").length).toBeGreaterThan(0);

    const rejectButtons = screen.getAllByRole("button", { name: /^Reject$/i });
    await user.click(rejectButtons[1]);

    await user.click(screen.getByRole("button", { name: /Generate anonymized text/i }));
    expect(await screen.findByText(/Anonymized preview/i)).toBeInTheDocument();
    expect(screen.getByText(/Email <EMAIL_ADDRESS> and 902-555-0182/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy to clipboard/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download .txt/i })).toBeInTheDocument();
  });

  it("shows API error state", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "analyzeText").mockRejectedValue(new Error("Analysis request failed."));
    render(<TextReviewWorkspace />);
    await setTextarea(/Text to analyze/i, "hello");
    await user.click(screen.getByRole("button", { name: /^Analyze text$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Analysis request failed.");
  });

  it("validates empty input", async () => {
    const user = userEvent.setup();
    render(<TextReviewWorkspace />);
    await user.click(screen.getByRole("button", { name: /^Analyze text$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Provide non-empty text");
  });

  it("loads fictional example", async () => {
    const user = userEvent.setup();
    render(<TextReviewWorkspace />);
    await user.click(screen.getByRole("button", { name: /Load fictional example/i }));
    await waitFor(() => {
      const value = (screen.getByLabelText(/Text to analyze/i) as HTMLTextAreaElement).value;
      expect(value).toContain("fictional.user@example.com");
    });
  });

  it("accepts visible detections", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "analyzeText").mockResolvedValue({
      text: "Email fictional.user@example.com",
      language: "en",
      detection_count: 1,
      entities: [
        {
          entity_type: "EMAIL_ADDRESS",
          start: 6,
          end: 32,
          text: "fictional.user@example.com",
          confidence: 0.95,
          detection_source: "regex",
          recognizer_name: "regex_email",
        },
      ],
    });
    render(<TextReviewWorkspace />);
    await setTextarea(/Text to analyze/i, "Email fictional.user@example.com");
    await user.click(screen.getByRole("button", { name: /^Analyze text$/i }));
    expect(await screen.findByText(/Detections \(/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Accept visible/i }));
    expect(screen.getByText("accepted")).toBeInTheDocument();
  });
});

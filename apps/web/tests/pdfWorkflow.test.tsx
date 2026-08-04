import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentWorkflow } from "@/features/upload/DocumentWorkflow";
import * as api from "@/lib/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

vi.mock("@/features/pdf/PdfPreview", () => ({
  PdfPreview: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid="pdf-preview">Preview page {pageNumber}</div>
  ),
}));

describe("PDF workflow UI", () => {
  it("opens PDF review after upload and analyzes", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "uploadDocument").mockResolvedValue({
      job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      status: "pending",
      file_type: "pdf",
      byte_size: 100,
      page_count: 1,
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
    });
    vi.spyOn(api, "analyzeDocument").mockResolvedValue({
      job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      status: "awaiting_review",
      page_count: 1,
      pages_with_text: 1,
      pages_needing_ocr: [],
      detection_count: 1,
      entities: [
        {
          id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
          entity_type: "EMAIL_ADDRESS",
          confidence: 0.9,
          detection_source: "regex",
          recognizer_name: "regex_email",
          start: 10,
          end: 36,
          text: "fictional.user@example.com",
          page_number: 1,
          rectangles: [{ x0: 10, y0: 20, x1: 100, y1: 40 }],
          review_status: "pending",
          anonymization_method: "redaction",
          manually_added: false,
          edited: false,
        },
      ],
    });
    vi.spyOn(api, "anonymizeDocument").mockResolvedValue({
      job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      status: "completed",
      artifact: {
        artifact_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
        job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        artifact_type: "redacted_pdf",
        byte_size: 120,
        created_at: "2026-08-03T12:05:00Z",
        expires_at: "2026-08-03T13:05:00Z",
      },
      redacted_count: 1,
      rejected_count: 0,
      warnings: [],
    });
    vi.spyOn(api, "fetchJobResult").mockResolvedValue({
      job_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      status: "completed",
      source_type: "pdf",
      output_type: "redacted_pdf",
      detection_count: 1,
      review_status_counts: { accepted: 1 },
      entity_category_counts: { EMAIL_ADDRESS: 1 },
      method_counts: { redaction: 1 },
      analysis_coverage: { total_pages: 1, embedded_text_pages: 1, ocr_pages: 0 },
      verification_status: "passed",
      warnings: [],
      artifact: {
        artifact_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
        artifact_type: "redacted_pdf",
        byte_size: 120,
        created_at: "2026-08-03T12:05:00Z",
        expires_at: "2026-08-03T13:05:00Z",
      },
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
      low_confidence_count: 0,
      ocr_used: false,
      page_count: 1,
    });

    render(<DocumentWorkflow onSwitchToText={() => undefined} />);
    const input = screen.getByLabelText(/browse files/i) as HTMLInputElement;
    const pdf = new File([new Uint8Array([1, 2, 3])], "fictional.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(input, { target: { files: [pdf] } });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    expect(await screen.findByText(/upload accepted/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /open pdf review/i }));
    expect(
      await screen.findByRole("heading", { name: /pdf review workspace/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /analyze pdf/i }));
    expect(await screen.findByText(/fictional\.user@example\.com/i)).toBeInTheDocument();
    expect(screen.getAllByText(/EMAIL_ADDRESS/i).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /generate redacted pdf/i }));
    expect(await screen.findByText(/processing complete/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download redacted pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download audit report/i })).toBeInTheDocument();
    expect(screen.queryByText(/storage_key/i)).not.toBeInTheDocument();
  });

  it("renders OCR_REQUIRED safely", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "uploadDocument").mockResolvedValue({
      job_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
      status: "pending",
      file_type: "pdf",
      byte_size: 50,
      page_count: 1,
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
    });
    const err = new Error(
      "This PDF appears to be image-based and requires OCR, which is unavailable for this request.",
    ) as api.ApiError;
    err.code = "OCR_REQUIRED";
    vi.spyOn(api, "analyzeDocument").mockRejectedValue(err);

    render(<DocumentWorkflow onSwitchToText={() => undefined} />);
    fireEvent.change(screen.getByLabelText(/browse files/i), {
      target: {
        files: [new File([new Uint8Array(8)], "scan.pdf", { type: "application/pdf" })],
      },
    });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    await user.click(await screen.findByRole("button", { name: /open pdf review/i }));
    await user.click(screen.getByRole("button", { name: /analyze pdf/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/OCR/i);
    expect(screen.getByText(/OCR_REQUIRED/)).toBeInTheDocument();
  });
});

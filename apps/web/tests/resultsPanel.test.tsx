/** Frontend-facing Vitest coverage for Phase 7 document results panel. */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentResultPanel } from "@/features/results/DocumentResultPanel";
import * as api from "@/lib/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DocumentResultPanel", () => {
  it("renders safe result summary and actions", async () => {
    vi.spyOn(api, "fetchJobResult").mockResolvedValue({
      job_id: "11111111-1111-4111-8111-111111111111",
      status: "completed",
      source_type: "pdf",
      output_type: "redacted_pdf",
      detection_count: 2,
      review_status_counts: { accepted: 1, rejected: 1 },
      entity_category_counts: { EMAIL_ADDRESS: 1, PERSON: 1 },
      method_counts: { redaction: 1 },
      analysis_coverage: {
        total_pages: 1,
        embedded_text_pages: 1,
        ocr_pages: 0,
      },
      verification_status: "passed",
      warnings: [],
      artifact: {
        artifact_id: "22222222-2222-4222-8222-222222222222",
        artifact_type: "redacted_pdf",
        byte_size: 1234,
        created_at: "2026-08-03T12:00:00+00:00",
        expires_at: "2026-08-03T13:00:00+00:00",
      },
      created_at: "2026-08-03T12:00:00+00:00",
      expires_at: "2026-08-03T13:00:00+00:00",
      low_confidence_count: 0,
      ocr_used: false,
      page_count: 1,
    });

    render(
      <DocumentResultPanel
        jobId="11111111-1111-4111-8111-111111111111"
        onReturnToReview={() => undefined}
        onDeleted={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Processing complete")).toBeTruthy();
    });
    expect(screen.getByText(/Verification: passed/)).toBeTruthy();
    expect(screen.getByText(/EMAIL_ADDRESS=1/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download output/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download audit report/i })).toBeTruthy();
    expect(screen.queryByText(/storage_key/i)).toBeNull();
    expect(screen.queryByText(/\/var\//i)).toBeNull();
  });

  it("shows deleted confirmation after delete-now", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "fetchJobResult").mockResolvedValue({
      job_id: "11111111-1111-4111-8111-111111111111",
      status: "completed",
      source_type: "pdf",
      output_type: "redacted_pdf",
      detection_count: 0,
      review_status_counts: {},
      entity_category_counts: {},
      method_counts: {},
      verification_status: "passed",
      warnings: [],
      artifact: {
        artifact_id: "22222222-2222-4222-8222-222222222222",
        artifact_type: "redacted_pdf",
        byte_size: 10,
        created_at: "2026-08-03T12:00:00+00:00",
        expires_at: "2026-08-03T13:00:00+00:00",
      },
      created_at: "2026-08-03T12:00:00+00:00",
      expires_at: "2026-08-03T13:00:00+00:00",
      low_confidence_count: 0,
      ocr_used: false,
      page_count: 1,
    });
    vi.spyOn(api, "deleteJob").mockResolvedValue({
      job_id: "11111111-1111-4111-8111-111111111111",
      deleted: true,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onDeleted = vi.fn();

    render(
      <DocumentResultPanel
        jobId="11111111-1111-4111-8111-111111111111"
        onReturnToReview={() => undefined}
        onDeleted={onDeleted}
      />,
    );

    await waitFor(() => expect(screen.getByText("Processing complete")).toBeTruthy());
    await user.click(screen.getByRole("button", { name: /Delete now/i }));
    await waitFor(() => expect(screen.getByText(/Job deleted/i)).toBeTruthy());
    expect(onDeleted).toHaveBeenCalled();
  });
});

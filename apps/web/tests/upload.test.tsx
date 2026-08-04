import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentUploadPanel } from "@/features/upload/DocumentUploadPanel";
import { HomeWorkspace } from "@/features/workspace/HomeWorkspace";
import * as api from "@/lib/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

function makeFile(name: string, type: string, size = 128): File {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
}

describe("HomeWorkspace mode selection", () => {
  it("switches between pasted text and document upload", async () => {
    const user = userEvent.setup();
    render(<HomeWorkspace />);
    expect(screen.getByRole("button", { name: /pasted text/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: /document upload/i }));
    expect(await screen.findByRole("heading", { name: /document upload/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/or browse files/i)).toBeInTheDocument();
  });
});

describe("DocumentUploadPanel", () => {
  it("exposes an accessible file input and accepted types", async () => {
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    const input = screen.getByLabelText(/browse files/i) as HTMLInputElement;
    expect(input).toHaveAttribute("type", "file");
    expect(input.accept).toContain(".pdf");
    expect(screen.getByText(/max size/i)).toBeInTheDocument();
  });

  it("rejects unsupported extensions client-side", async () => {
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    const input = screen.getByLabelText(/browse files/i) as HTMLInputElement;
    const bad = makeFile("notes.exe", "application/octet-stream");
    fireEvent.change(input, { target: { files: [bad] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/supported types/i);
  });

  it("rejects oversized files client-side", async () => {
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    const input = screen.getByLabelText(/browse files/i) as HTMLInputElement;
    const big = makeFile("huge.pdf", "application/pdf", api.MAX_UPLOAD_BYTES + 1);
    fireEvent.change(input, { target: { files: [big] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/maximum size/i);
  });

  it("selects a valid PDF and allows removal", async () => {
    const user = userEvent.setup();
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    const input = screen.getByLabelText(/browse files/i) as HTMLInputElement;
    const pdf = makeFile("fictional-report.pdf", "application/pdf", 512);
    fireEvent.change(input, { target: { files: [pdf] } });
    expect(await screen.findByText(/fictional-report\.pdf/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /remove file/i }));
    expect(screen.queryByText(/fictional-report\.pdf/i)).not.toBeInTheDocument();
  });

  it("supports drag-and-drop selection for PNG", async () => {
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    const dropzone = screen.getByRole("button", { name: /drop a pdf/i });
    const png = makeFile("sample.png", "image/png", 256);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [png] },
    });
    expect(await screen.findByText(/sample\.png/i)).toBeInTheDocument();
  });

  it("uploads successfully and renders safe metadata only", async () => {
    const user = userEvent.setup();
    const uploadSpy = vi.spyOn(api, "uploadDocument").mockResolvedValue({
      job_id: "11111111-1111-1111-1111-111111111111",
      status: "pending",
      file_type: "pdf",
      byte_size: 512,
      page_count: 1,
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
    });
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    const input = screen.getByLabelText(/browse files/i) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeFile("fictional-report.pdf", "application/pdf", 512)] },
    });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    expect(await screen.findByText(/upload accepted/i)).toBeInTheDocument();
    expect(screen.getByText(/11111111-1111-1111-1111-111111111111/)).toBeInTheDocument();
    expect(screen.getByText(/pending/i)).toBeInTheDocument();
    expect(screen.queryByText(/storage_key/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/tmp\//i)).not.toBeInTheDocument();
    expect(uploadSpy).toHaveBeenCalledOnce();
  });

  it("shows loading and backend error codes", async () => {
    const user = userEvent.setup();
    let resolveUpload: (value: api.JobMetadata) => void = () => undefined;
    vi.spyOn(api, "uploadDocument").mockImplementation(
      () =>
        new Promise<api.JobMetadata>((resolve) => {
          resolveUpload = resolve;
        }),
    );
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    fireEvent.change(screen.getByLabelText(/browse files/i), {
      target: { files: [makeFile("ok.pdf", "application/pdf")] },
    });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/working/i);
    resolveUpload({
      job_id: "22222222-2222-2222-2222-222222222222",
      status: "pending",
      file_type: "pdf",
      byte_size: 10,
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
    });
    await waitFor(() => expect(screen.getByText(/upload accepted/i)).toBeInTheDocument());

    const err = new Error("Password-protected PDFs are not accepted.") as api.ApiError;
    err.code = "PASSWORD_PROTECTED_PDF";
    vi.spyOn(api, "uploadDocument").mockRejectedValue(err);
    fireEvent.change(screen.getByLabelText(/browse files/i), {
      target: { files: [makeFile("locked.pdf", "application/pdf")] },
    });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/password-protected/i);
    expect(screen.getByText(/PASSWORD_PROTECTED_PDF/)).toBeInTheDocument();
  });

  it("deletes a job and confirms inaccessibility", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(api, "uploadDocument").mockResolvedValue({
      job_id: "33333333-3333-3333-3333-333333333333",
      status: "pending",
      file_type: "png",
      byte_size: 64,
      image_width: 8,
      image_height: 8,
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
    });
    vi.spyOn(api, "deleteJob").mockResolvedValue({
      job_id: "33333333-3333-3333-3333-333333333333",
      deleted: true,
    });
    const notFound = new Error("Job not found.") as api.ApiError;
    notFound.code = "JOB_NOT_FOUND";
    vi.spyOn(api, "fetchJob").mockRejectedValue(notFound);

    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    fireEvent.change(screen.getByLabelText(/browse files/i), {
      target: { files: [makeFile("pixel.png", "image/png")] },
    });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    await screen.findByText(/upload accepted/i);
    await user.click(screen.getByRole("button", { name: /delete now/i }));
    expect(await screen.findByText(/job was deleted/i)).toBeInTheDocument();
    expect(screen.getByText(/no longer accessible/i)).toBeInTheDocument();
  });

  it("does not persist file or job ids in browser storage", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "uploadDocument").mockResolvedValue({
      job_id: "44444444-4444-4444-4444-444444444444",
      status: "pending",
      file_type: "jpeg",
      byte_size: 32,
      image_width: 4,
      image_height: 4,
      created_at: "2026-08-03T12:00:00Z",
      expires_at: "2026-08-03T13:00:00Z",
    });
    render(<DocumentUploadPanel onSwitchToText={() => undefined} />);
    fireEvent.change(screen.getByLabelText(/browse files/i), {
      target: { files: [makeFile("shot.jpeg", "image/jpeg")] },
    });
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    await screen.findByText(/upload accepted/i);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

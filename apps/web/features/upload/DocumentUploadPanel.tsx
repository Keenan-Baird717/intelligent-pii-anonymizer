"use client";

import { useId, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";

import {
  ACCEPTED_UPLOAD_ACCEPT,
  ACCEPTED_UPLOAD_EXTENSIONS,
  deleteJob,
  fetchJob,
  MAX_UPLOAD_BYTES,
  uploadDocument,
  type ApiError,
  type JobMetadata,
} from "@/lib/api";

type UploadPanelProps = {
  onSwitchToText: () => void;
  onJobReady?: (job: JobMetadata) => void;
  onAnalyzePdf?: (job: JobMetadata) => void;
  onOpenImageReview?: (job: JobMetadata) => void;
  activeJob?: JobMetadata | null;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function extensionOf(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx >= 0 ? name.slice(idx).toLowerCase() : "";
}

function clientValidate(file: File): string | null {
  const ext = extensionOf(file.name);
  if (!(ACCEPTED_UPLOAD_EXTENSIONS as readonly string[]).includes(ext)) {
    return "Supported types: PDF, PNG, JPG, and JPEG only.";
  }
  if (file.size <= 0) {
    return "The selected file is empty.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File exceeds the maximum size of ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  return null;
}

export function DocumentUploadPanel({
  onSwitchToText,
  onJobReady,
  onAnalyzePdf,
  onOpenImageReview,
  activeJob = null,
}: UploadPanelProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [job, setJob] = useState<JobMetadata | null>(activeJob);
  const [deleted, setDeleted] = useState(false);
  const [inaccessible, setInaccessible] = useState(false);

  function clearSelection() {
    setFile(null);
    setError(null);
    setErrorCode(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function selectFile(next: File | null) {
    setJob(null);
    setDeleted(false);
    setInaccessible(false);
    setError(null);
    setErrorCode(null);
    if (!next) {
      setFile(null);
      return;
    }
    const validationError = clientValidate(next);
    if (validationError) {
      setFile(null);
      setError(validationError);
      return;
    }
    setFile(next);
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0] ?? null;
    selectFile(chosen);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    const chosen = event.dataTransfer.files?.[0] ?? null;
    selectFile(chosen);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose a PDF, PNG, JPG, or JPEG file to upload.");
      return;
    }
    setLoading(true);
    setError(null);
    setErrorCode(null);
    setDeleted(false);
    setInaccessible(false);
    try {
      const result = await uploadDocument(file);
      setJob(result);
      onJobReady?.(result);
    } catch (err) {
      const apiErr = err as ApiError;
      setJob(null);
      setError(apiErr.message || "Document upload failed.");
      setErrorCode(apiErr.code ?? null);
    } finally {
      setLoading(false);
    }
  }

  async function onDelete() {
    if (!job) return;
    if (!window.confirm("Delete this uploaded job and its temporary file now?")) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await deleteJob(job.job_id);
      setDeleted(true);
      setJob(null);
      try {
        await fetchJob(job.job_id);
        setInaccessible(false);
      } catch {
        setInaccessible(true);
      }
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || "Job deletion failed.");
      setErrorCode(apiErr.code ?? null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-6" aria-labelledby="upload-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="upload-heading" className="text-xl font-semibold">
            Document upload
          </h2>
          <p className="text-sm text-slate-600">
            Secure temporary storage only. Document analysis will be added in the next phase.
          </p>
        </div>
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-sm"
          onClick={onSwitchToText}
        >
          Switch to pasted text
        </button>
      </div>

      <form className="space-y-4" onSubmit={onSubmit}>
        <div
          role="button"
          tabIndex={0}
          aria-label="Drop a PDF, PNG, JPG, or JPEG file here, or press Enter to browse"
          className={`rounded-lg border-2 border-dashed p-8 text-center transition ${
            dragActive ? "border-slate-700 bg-slate-50" : "border-slate-300 bg-white"
          }`}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragActive(false);
          }}
          onDrop={onDrop}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              inputRef.current?.click();
            }
          }}
        >
          <p className="font-medium">Drag and drop one file here</p>
          <p className="mt-1 text-sm text-slate-600">
            Accepted: PDF, PNG, JPG, JPEG · Max size: {formatBytes(MAX_UPLOAD_BYTES)}
          </p>
          <label htmlFor={inputId} className="mt-4 inline-block cursor-pointer text-sm underline">
            Or browse files
          </label>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            className="sr-only"
            accept={ACCEPTED_UPLOAD_ACCEPT}
            onChange={onInputChange}
          />
        </div>

        {file ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-slate-50 px-3 py-2 text-sm">
            <p>
              Selected: <span className="font-medium">{file.name}</span> ({formatBytes(file.size)})
            </p>
            <button type="button" className="underline" onClick={clearSelection}>
              Remove file
            </button>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={loading || !file}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Uploading…" : "Upload document"}
        </button>
      </form>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <p>{error}</p>
          {errorCode ? <p className="mt-1 text-xs">Error code: {errorCode}</p> : null}
        </div>
      ) : null}

      {loading ? (
        <p role="status" aria-live="polite" className="text-sm text-slate-600">
          Working…
        </p>
      ) : null}

      {job ? (
        <div className="space-y-3 rounded-lg border bg-white p-4 text-sm" aria-live="polite">
          <h3 className="font-semibold">Upload accepted</h3>
          <dl className="grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="text-slate-500">Job ID</dt>
              <dd className="font-mono text-xs">{job.job_id}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Status</dt>
              <dd>{job.status}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Validated type</dt>
              <dd>{job.file_type}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Size</dt>
              <dd>{formatBytes(job.byte_size)}</dd>
            </div>
            {job.page_count != null ? (
              <div>
                <dt className="text-slate-500">Pages</dt>
                <dd>{job.page_count}</dd>
              </div>
            ) : null}
            {job.image_width != null && job.image_height != null ? (
              <div>
                <dt className="text-slate-500">Dimensions</dt>
                <dd>
                  {job.image_width} × {job.image_height}
                </dd>
              </div>
            ) : null}
            <div>
              <dt className="text-slate-500">Expires</dt>
              <dd>{new Date(job.expires_at).toLocaleString()}</dd>
            </div>
          </dl>
          <p className="text-slate-600">
            {job.file_type === "pdf"
              ? "Text-based and scanned PDF analysis with true redaction are available next."
              : "Image OCR analysis and irreversible redaction are available next."}
          </p>
          <div className="flex flex-wrap gap-2">
            {job.file_type === "pdf" && onAnalyzePdf ? (
              <button
                type="button"
                className="rounded-md bg-slate-900 px-3 py-2 text-white"
                onClick={() => onAnalyzePdf(job)}
                disabled={loading}
              >
                Open PDF review
              </button>
            ) : null}
            {(job.file_type === "png" || job.file_type === "jpeg") && onOpenImageReview ? (
              <button
                type="button"
                className="rounded-md bg-slate-900 px-3 py-2 text-white"
                onClick={() => onOpenImageReview(job)}
                disabled={loading}
              >
                Open image review
              </button>
            ) : null}
            <button
              type="button"
              className="rounded-md border border-red-300 px-3 py-2 text-red-800"
              onClick={onDelete}
              disabled={loading}
            >
              Delete now
            </button>
          </div>
        </div>
      ) : null}

      {deleted ? (
        <div
          role="status"
          className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900"
        >
          <p>The job was deleted. Temporary file and metadata were removed.</p>
          {inaccessible ? (
            <p className="mt-1">Confirmed: the job is no longer accessible.</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

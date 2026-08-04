"use client";

import { useEffect, useState } from "react";

import {
  artifactDownloadUrl,
  auditReportUrl,
  deleteJob,
  fetchJobResult,
  type JobResultSummary,
} from "@/lib/api";

type Props = {
  jobId: string;
  onReturnToReview: () => void;
  onDeleted: () => void;
  downloadLabel?: string;
};

export function DocumentResultPanel({
  jobId,
  onReturnToReview,
  onDeleted,
  downloadLabel = "Download output",
}: Props) {
  const [result, setResult] = useState<JobResultSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleted, setDeleted] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchJobResult(jobId)
      .then((summary) => {
        if (!cancelled) setResult(summary);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Result unavailable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function onDelete() {
    if (!window.confirm("Delete this job and all related files now?")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteJob(jobId);
      setDeleted(true);
      setResult(null);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setBusy(false);
    }
  }

  if (deleted) {
    return (
      <div className="rounded-lg border bg-slate-50 p-4 text-sm" role="status" aria-live="polite">
        <h3 className="font-semibold text-slate-900">Job deleted</h3>
        <p className="mt-1 text-slate-600">
          All job data, artifacts, and temporary files have been removed. This job is no longer
          accessible.
        </p>
      </div>
    );
  }

  if (error && !result) {
    return (
      <div
        className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"
        role="alert"
      >
        <h3 className="font-semibold">Result unavailable</h3>
        <p className="mt-1">{error}</p>
        <button type="button" className="mt-3 rounded border px-3 py-1" onClick={onReturnToReview}>
          Return to review
        </button>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="rounded-lg border bg-slate-50 p-4 text-sm text-slate-600" aria-live="polite">
        Loading result summary…
      </div>
    );
  }

  const verification = result.verification_status ?? "unknown";
  const artifact = result.artifact;
  const downloadHref = artifact != null ? artifactDownloadUrl(jobId, artifact.artifact_id) : null;
  const coverage = result.analysis_coverage ?? {};

  return (
    <div
      className="space-y-3 rounded-lg border bg-emerald-50 p-4 text-sm text-emerald-950"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">Processing complete</h3>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            verification === "passed"
              ? "bg-emerald-200 text-emerald-950"
              : verification === "failed"
                ? "bg-red-200 text-red-950"
                : "bg-slate-200 text-slate-800"
          }`}
        >
          Verification: {verification}
        </span>
      </div>

      <dl className="grid gap-1 sm:grid-cols-2">
        <div>
          <dt className="text-emerald-800/80">Status</dt>
          <dd>{result.status}</dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Output type</dt>
          <dd>{result.output_type ?? "n/a"}</dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Detections</dt>
          <dd>{result.detection_count}</dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Review counts</dt>
          <dd>
            {Object.entries(result.review_status_counts)
              .map(([key, value]) => `${key}=${value}`)
              .join(", ") || "none"}
          </dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Categories</dt>
          <dd>
            {Object.entries(result.entity_category_counts)
              .map(([key, value]) => `${key}=${value}`)
              .join(", ") || "none"}
          </dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Methods</dt>
          <dd>
            {Object.entries(result.method_counts)
              .map(([key, value]) => `${key}=${value}`)
              .join(", ") || "none"}
          </dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">OCR used</dt>
          <dd>{result.ocr_used ? "yes" : "no"}</dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Page coverage</dt>
          <dd>
            pages={String(coverage.total_pages ?? result.page_count ?? "n/a")}, embedded=
            {String(coverage.embedded_text_pages ?? "n/a")}, ocr=
            {String(coverage.ocr_pages ?? "n/a")}
          </dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Low-confidence warnings</dt>
          <dd>{result.low_confidence_count}</dd>
        </div>
        <div>
          <dt className="text-emerald-800/80">Expires</dt>
          <dd>{new Date(result.expires_at).toLocaleString()}</dd>
        </div>
        {artifact ? (
          <div>
            <dt className="text-emerald-800/80">Artifact</dt>
            <dd>
              {artifact.artifact_type} · {artifact.byte_size} bytes
            </dd>
          </div>
        ) : null}
      </dl>

      {result.warnings.length > 0 ? (
        <p className="text-amber-900">Safe warnings: {result.warnings.join(", ")}</p>
      ) : null}

      {error ? <p className="text-red-800">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        {downloadHref ? (
          <a className="rounded-md bg-slate-900 px-4 py-2 text-white" href={downloadHref} download>
            {downloadLabel}
          </a>
        ) : null}
        <a
          className="rounded-md border border-emerald-800 px-4 py-2 text-emerald-950"
          href={auditReportUrl(jobId)}
          download="anonymization-audit-report.json"
        >
          Download audit report
        </a>
        <button type="button" className="rounded-md border px-4 py-2" onClick={onReturnToReview}>
          Return to review
        </button>
        <button
          type="button"
          className="rounded-md border border-red-400 px-4 py-2 text-red-900"
          onClick={() => void onDelete()}
          disabled={busy}
        >
          {busy ? "Deleting…" : "Delete now"}
        </button>
      </div>
    </div>
  );
}

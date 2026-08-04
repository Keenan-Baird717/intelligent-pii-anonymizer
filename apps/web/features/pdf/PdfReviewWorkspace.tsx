"use client";

import { useMemo, useState } from "react";

import {
  analyzeDocument,
  anonymizeDocument,
  createManualRedaction,
  deleteDocumentEntity,
  deleteJob,
  jobSourcePdfUrl,
  patchDocumentEntity,
  type ApiError,
  type ArtifactMetadata,
  type DocumentEntity,
  type JobMetadata,
  type PdfRect,
} from "@/lib/api";
import { DocumentResultPanel } from "@/features/results/DocumentResultPanel";
import { ENTITY_TYPES } from "@/features/review/types";
import { PdfPreview } from "./PdfPreview";

type PdfReviewWorkspaceProps = {
  job: JobMetadata;
  onDeleted: () => void;
  onBack: () => void;
};

export function PdfReviewWorkspace({ job, onDeleted, onBack }: PdfReviewWorkspaceProps) {
  const [entities, setEntities] = useState<DocumentEntity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.25);
  const [drawMode, setDrawMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [analyzed, setAnalyzed] = useState(false);
  const [artifact, setArtifact] = useState<ArtifactMetadata | null>(null);
  const pageCount = job.page_count ?? 1;

  const selected = useMemo(
    () => entities.find((entity) => entity.id === selectedId) ?? null,
    [entities, selectedId],
  );

  async function runAnalyze() {
    setLoading(true);
    setError(null);
    setErrorCode(null);
    setWarning(null);
    setArtifact(null);
    try {
      const result = await analyzeDocument(job.job_id);
      setEntities(result.entities);
      setAnalyzed(true);
      if (result.warning_message) {
        setWarning(result.warning_message);
      } else if (result.coverage && !result.coverage.fully_analyzed) {
        setWarning("Some pages could not be analyzed. The document was not fully analyzed.");
      }
      if (result.entities[0]) {
        setPageNumber(result.entities[0].page_number);
        setSelectedId(result.entities[0].id);
      }
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || "Document analysis failed.");
      setErrorCode(apiErr.code ?? null);
      setAnalyzed(false);
    } finally {
      setLoading(false);
    }
  }

  async function setStatus(id: string, review_status: string) {
    const updated = await patchDocumentEntity(job.job_id, id, { review_status });
    setEntities((current) => current.map((entity) => (entity.id === id ? updated : entity)));
  }

  async function setType(id: string, entity_type: string) {
    const updated = await patchDocumentEntity(job.job_id, id, {
      entity_type,
      review_status: "edited",
    });
    setEntities((current) => current.map((entity) => (entity.id === id ? updated : entity)));
  }

  async function onManualRect(page: number, rectangle: PdfRect) {
    setLoading(true);
    setError(null);
    try {
      const created = await createManualRedaction(job.job_id, {
        page_number: page,
        rectangle,
        entity_type: "OTHER",
      });
      setEntities((current) => [...current, created]);
      setSelectedId(created.id);
      setDrawMode(false);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || "Manual redaction failed.");
      setErrorCode(apiErr.code ?? null);
    } finally {
      setLoading(false);
    }
  }

  async function removeManual(id: string) {
    await deleteDocumentEntity(job.job_id, id);
    setEntities((current) => current.filter((entity) => entity.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  async function runRedact() {
    setLoading(true);
    setError(null);
    setErrorCode(null);
    try {
      const result = await anonymizeDocument(job.job_id);
      setArtifact(result.artifact);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || "Document redaction failed.");
      setErrorCode(apiErr.code ?? null);
      setArtifact(null);
    } finally {
      setLoading(false);
    }
  }

  async function onDeleteJob() {
    if (!window.confirm("Delete this job, original PDF, and any generated artifacts now?")) {
      return;
    }
    setLoading(true);
    try {
      await deleteJob(job.job_id);
      onDeleted();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || "Delete failed.");
      setErrorCode(apiErr.code ?? null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-4" aria-labelledby="pdf-review-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="pdf-review-heading" className="text-xl font-semibold">
            PDF review workspace
          </h2>
          <p className="text-sm text-slate-600">
            Text-based and scanned PDFs. True redaction removes accepted content from a new PDF. OCR
            may miss handwriting, complex layouts, or low-resolution text — review carefully.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-md border px-3 py-2 text-sm" onClick={onBack}>
            Back to upload
          </button>
          <button
            type="button"
            className="rounded-md border border-red-300 px-3 py-2 text-sm text-red-800"
            onClick={onDeleteJob}
            disabled={loading}
          >
            Delete now
          </button>
        </div>
      </div>

      <dl className="grid gap-2 rounded-md border bg-slate-50 p-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Job ID</dt>
          <dd className="font-mono text-xs">{job.job_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Pages</dt>
          <dd>{job.page_count ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Status</dt>
          <dd>{job.status}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          onClick={runAnalyze}
          disabled={loading}
        >
          {loading && !analyzed ? "Analyzing…" : "Analyze PDF"}
        </button>
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-sm"
          onClick={() => setPageNumber((value) => Math.max(1, value - 1))}
          disabled={pageNumber <= 1}
        >
          Previous page
        </button>
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-sm"
          onClick={() => setPageNumber((value) => Math.min(pageCount, value + 1))}
          disabled={pageNumber >= pageCount}
        >
          Next page
        </button>
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-sm"
          onClick={() => setScale((value) => Math.max(0.5, Number((value - 0.25).toFixed(2))))}
        >
          Zoom out
        </button>
        <button
          type="button"
          className="rounded-md border px-3 py-2 text-sm"
          onClick={() => setScale((value) => Math.min(3, Number((value + 0.25).toFixed(2))))}
        >
          Zoom in
        </button>
        <button
          type="button"
          className={`rounded-md px-3 py-2 text-sm ${drawMode ? "bg-amber-600 text-white" : "border"}`}
          onClick={() => setDrawMode((value) => !value)}
          aria-pressed={drawMode}
          disabled={!analyzed}
        >
          {drawMode ? "Drawing manual region…" : "Add manual rectangle"}
        </button>
        <button
          type="button"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          onClick={runRedact}
          disabled={loading || !analyzed}
        >
          Generate redacted PDF
        </button>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <p>{error}</p>
          {errorCode ? <p className="mt-1 text-xs">Error code: {errorCode}</p> : null}
        </div>
      ) : null}
      {warning ? (
        <div
          role="status"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          {warning}
        </div>
      ) : null}
      {loading ? (
        <p role="status" className="text-sm text-slate-600">
          Working…
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <PdfPreview
          sourceUrl={jobSourcePdfUrl(job.job_id)}
          pageNumber={pageNumber}
          scale={scale}
          entities={entities}
          selectedId={selectedId}
          onSelectEntity={(id) => {
            setSelectedId(id);
            const entity = entities.find((item) => item.id === id);
            if (entity) setPageNumber(entity.page_number);
          }}
          drawMode={drawMode}
          onManualRect={onManualRect}
        />

        <div className="space-y-3">
          <h3 className="font-semibold">Detections ({entities.length})</h3>
          <p className="text-xs text-slate-600">
            PDF output uses true redaction only. Masking, replacement, and pseudonymization remain
            available for pasted text.
          </p>
          <ul className="max-h-[32rem] space-y-2 overflow-auto">
            {entities.map((entity) => (
              <li key={entity.id}>
                <button
                  type="button"
                  className={`w-full rounded-md border p-2 text-left text-sm ${
                    selectedId === entity.id ? "border-slate-900 bg-slate-50" : ""
                  }`}
                  onClick={() => {
                    setSelectedId(entity.id);
                    setPageNumber(entity.page_number);
                  }}
                >
                  <div className="font-medium">
                    {entity.entity_type} · p.{entity.page_number}
                    {entity.source_kind ? ` · ${entity.source_kind}` : ""}
                  </div>
                  <div className="text-xs text-slate-600">
                    {entity.manually_added
                      ? "Manual rectangle"
                      : entity.text
                        ? entity.text
                        : "(no preview text)"}
                  </div>
                  <div className="text-xs">
                    {entity.review_status}
                    {entity.confidence != null
                      ? ` · det ${(entity.confidence * 100).toFixed(0)}%`
                      : ""}
                    {entity.ocr_confidence != null
                      ? ` · ocr ${(entity.ocr_confidence * 100).toFixed(0)}%`
                      : ""}
                    {entity.low_ocr_confidence ? " · low OCR confidence" : ""}
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <label className="block">
                <span className="text-slate-500">Entity type</span>
                <select
                  className="mt-1 w-full rounded border px-2 py-1"
                  value={selected.entity_type}
                  onChange={(event) => void setType(selected.id, event.target.value)}
                >
                  {ENTITY_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded border px-2 py-1"
                  onClick={() => void setStatus(selected.id, "accepted")}
                >
                  Accept
                </button>
                <button
                  type="button"
                  className="rounded border px-2 py-1"
                  onClick={() => void setStatus(selected.id, "rejected")}
                >
                  Reject
                </button>
                {selected.manually_added ? (
                  <button
                    type="button"
                    className="rounded border border-red-300 px-2 py-1 text-red-800"
                    onClick={() => void removeManual(selected.id)}
                  >
                    Delete manual
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {artifact ? (
        <DocumentResultPanel
          jobId={job.job_id}
          downloadLabel="Download redacted PDF"
          onReturnToReview={() => setArtifact(null)}
          onDeleted={onDeleted}
        />
      ) : null}
    </section>
  );
}

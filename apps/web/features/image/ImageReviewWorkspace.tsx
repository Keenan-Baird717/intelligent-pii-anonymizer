"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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

const ENTITY_TYPES = [
  "PERSON",
  "EMAIL_ADDRESS",
  "PHONE_NUMBER",
  "LOCATION",
  "CA_POSTAL_CODE",
  "CA_SIN",
  "CREDIT_CARD",
  "DATE_TIME",
  "ORGANIZATION",
  "OTHER",
];

type Props = {
  job: JobMetadata;
  onDeleted: () => void;
  onBack: () => void;
};

export function ImageReviewWorkspace({ job, onDeleted, onBack }: Props) {
  const [entities, setEntities] = useState<DocumentEntity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [drawMode, setDrawMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [coverageNote, setCoverageNote] = useState<string | null>(null);
  const [analyzed, setAnalyzed] = useState(false);
  const [artifact, setArtifact] = useState<ArtifactMetadata | null>(null);
  const [naturalSize, setNaturalSize] = useState({
    width: job.image_width ?? 0,
    height: job.image_height ?? 0,
  });
  const imgRef = useRef<HTMLImageElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<PdfRect | null>(null);

  const selected = useMemo(
    () => entities.find((entity) => entity.id === selectedId) ?? null,
    [entities, selectedId],
  );

  const sourceUrl = jobSourcePdfUrl(job.job_id);

  async function runAnalyze() {
    setLoading(true);
    setError(null);
    setErrorCode(null);
    setWarning(null);
    setCoverageNote(null);
    setArtifact(null);
    try {
      const result = await analyzeDocument(job.job_id);
      setEntities(result.entities);
      setAnalyzed(true);
      if (result.warning_message) setWarning(result.warning_message);
      if (result.coverage) {
        if (!result.coverage.fully_analyzed) {
          setCoverageNote("This image was not fully analyzed. Review carefully before sharing.");
        } else if (result.coverage.low_confidence_warning) {
          setCoverageNote(
            "OCR confidence is low. Automated detection may miss sensitive information.",
          );
        }
      }
      if (result.entities[0]) setSelectedId(result.entities[0].id);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || "Image analysis failed.");
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

  async function onManualRect(rectangle: PdfRect) {
    setLoading(true);
    setError(null);
    try {
      const created = await createManualRedaction(job.job_id, {
        page_number: 1,
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
      setError(apiErr.message || "Image redaction failed.");
      setErrorCode(apiErr.code ?? null);
      setArtifact(null);
    } finally {
      setLoading(false);
    }
  }

  async function onDeleteJob() {
    if (!window.confirm("Delete this job, original image, and any generated artifacts now?")) {
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

  function toImageRect(
    clientX: number,
    clientY: number,
    endX: number,
    endY: number,
  ): PdfRect | null {
    const img = imgRef.current;
    if (!img || !naturalSize.width) return null;
    const bounds = img.getBoundingClientRect();
    const x0v = Math.min(clientX, endX) - bounds.left;
    const y0v = Math.min(clientY, endY) - bounds.top;
    const x1v = Math.max(clientX, endX) - bounds.left;
    const y1v = Math.max(clientY, endY) - bounds.top;
    if (x1v - x0v < 2 || y1v - y0v < 2) return null;
    const sx = naturalSize.width / bounds.width;
    const sy = naturalSize.height / bounds.height;
    return { x0: x0v * sx, y0: y0v * sy, x1: x1v * sx, y1: y1v * sy };
  }

  const displayEntities = entities.filter(
    (entity) => entity.review_status !== "rejected" && entity.rectangles.length > 0,
  );

  return (
    <section className="space-y-4" aria-labelledby="image-review-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="image-review-heading" className="text-xl font-semibold">
            Image review workspace
          </h2>
          <p className="text-sm text-slate-600">
            OCR-derived detections use image-pixel coordinates. Manual rectangles remain available
            when OCR misses sensitive content. OCR may miss handwriting or low-resolution text.
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

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          onClick={runAnalyze}
          disabled={loading}
        >
          {loading && !analyzed ? "Analyzing…" : "Analyze image"}
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
          Generate redacted image
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
      {warning || coverageNote ? (
        <div
          role="status"
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          {warning || coverageNote}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div
          className="relative inline-block max-w-full overflow-auto rounded border bg-slate-100"
          aria-label="Image draw surface"
          onPointerDown={(event) => {
            if (!drawMode) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            dragStart.current = { x: event.clientX, y: event.clientY };
            setDraft(null);
          }}
          onPointerMove={(event) => {
            if (!drawMode || !dragStart.current) return;
            setDraft(
              toImageRect(dragStart.current.x, dragStart.current.y, event.clientX, event.clientY),
            );
          }}
          onPointerUp={(event) => {
            if (!drawMode || !dragStart.current) return;
            const rect = toImageRect(
              dragStart.current.x,
              dragStart.current.y,
              event.clientX,
              event.clientY,
            );
            dragStart.current = null;
            setDraft(null);
            if (rect) void onManualRect(rect);
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            ref={imgRef}
            src={sourceUrl}
            alt="Uploaded image preview"
            style={{ width: naturalSize.width ? naturalSize.width * scale : undefined }}
            className="block max-w-none"
            onLoad={(event) => {
              const target = event.currentTarget;
              setNaturalSize({ width: target.naturalWidth, height: target.naturalHeight });
            }}
          />
          <div className="pointer-events-none absolute inset-0">
            {displayEntities.map((entity) =>
              entity.rectangles.map((rect, index) => {
                const left = rect.x0 * scale;
                const top = rect.y0 * scale;
                const width = (rect.x1 - rect.x0) * scale;
                const height = (rect.y1 - rect.y0) * scale;
                const low = Boolean(entity.low_ocr_confidence);
                return (
                  <button
                    key={`${entity.id}-${index}`}
                    type="button"
                    className={`absolute border-2 ${
                      drawMode ? "pointer-events-none" : "pointer-events-auto"
                    } ${
                      entity.manually_added
                        ? "border-amber-600 bg-amber-400/40"
                        : low
                          ? "border-rose-600 bg-rose-400/30"
                          : "border-sky-600 bg-sky-400/30"
                    }`}
                    style={{ left, top, width, height }}
                    aria-label={`Detection ${entity.entity_type} on image`}
                    onClick={() => setSelectedId(entity.id)}
                  />
                );
              }),
            )}
            {draft ? (
              <div
                className="absolute border-2 border-dashed border-amber-600 bg-amber-300/30"
                style={{
                  left: draft.x0 * scale,
                  top: draft.y0 * scale,
                  width: (draft.x1 - draft.x0) * scale,
                  height: (draft.y1 - draft.y0) * scale,
                }}
              />
            ) : null}
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="font-semibold">Detections ({entities.length})</h3>
          <ul className="max-h-[32rem] space-y-2 overflow-auto">
            {entities.map((entity) => (
              <li key={entity.id}>
                <button
                  type="button"
                  className={`w-full rounded-md border p-2 text-left text-sm ${
                    selectedId === entity.id ? "border-slate-900 bg-slate-50" : ""
                  }`}
                  onClick={() => setSelectedId(entity.id)}
                >
                  <div className="font-medium">
                    {entity.entity_type}
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
          downloadLabel="Download redacted image"
          onReturnToReview={() => setArtifact(null)}
          onDeleted={onDeleted}
        />
      ) : null}
    </section>
  );
}

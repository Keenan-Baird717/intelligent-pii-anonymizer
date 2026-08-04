"use client";

import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";

import type { DocumentEntity, PdfRect } from "@/lib/api";

// Same-origin worker (no CDN) — required for a practical CSP without third-party script hosts.
GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

type PdfPreviewProps = {
  sourceUrl: string;
  pageNumber: number;
  scale: number;
  entities: DocumentEntity[];
  selectedId: string | null;
  onSelectEntity: (id: string) => void;
  drawMode: boolean;
  onManualRect: (pageNumber: number, rect: PdfRect) => void;
};

function overlayClass(entity: DocumentEntity, selected: boolean): string {
  if (entity.review_status === "rejected") {
    return "border-slate-300 bg-slate-200/20";
  }
  if (entity.manually_added) {
    return selected ? "border-amber-600 bg-amber-400/40" : "border-amber-500 bg-amber-300/30";
  }
  return selected ? "border-sky-700 bg-sky-400/40" : "border-sky-500 bg-sky-300/30";
}

export function PdfPreview({
  sourceUrl,
  pageNumber,
  scale,
  entities,
  selectedId,
  onSelectEntity,
  drawMode,
  onManualRect,
}: PdfPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<PdfRect | null>(null);

  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    setLoading(true);
    setError(null);
    setPdf(null);
    const task = getDocument(sourceUrl);
    task.promise
      .then((doc) => {
        if (cancelled) {
          void doc.destroy();
          return;
        }
        loaded = doc;
        setPdf(doc);
        setPageCount(doc.numPages);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Unable to render the PDF preview.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      void task.destroy();
      if (loaded) {
        void loaded.destroy();
      }
      setPdf(null);
    };
  }, [sourceUrl]);

  useEffect(() => {
    if (!pdf || !canvasRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;
        const context = canvas.getContext("2d");
        if (!context) return;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        setPageSize({ width: viewport.width, height: viewport.height });
        await page.render({ canvasContext: context, viewport }).promise;
      } catch {
        if (!cancelled) setError("Unable to render this page.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdf, pageNumber, scale]);

  const pageEntities = entities.filter(
    (entity) =>
      entity.page_number === pageNumber &&
      entity.review_status !== "rejected" &&
      entity.rectangles.length > 0,
  );

  function toPdfRect(clientX: number, clientY: number, endX: number, endY: number): PdfRect | null {
    const canvas = canvasRef.current;
    if (!canvas || !pdf) return null;
    const bounds = canvas.getBoundingClientRect();
    const x0v = Math.min(clientX, endX) - bounds.left;
    const y0v = Math.min(clientY, endY) - bounds.top;
    const x1v = Math.max(clientX, endX) - bounds.left;
    const y1v = Math.max(clientY, endY) - bounds.top;
    if (x1v - x0v < 2 || y1v - y0v < 2) return null;
    // PDF.js viewport uses top-left; PDF user space is bottom-left.
    const pageHeight = pageSize.height / scale;
    const x0 = x0v / scale;
    const x1 = x1v / scale;
    const y0 = pageHeight - y1v / scale;
    const y1 = pageHeight - y0v / scale;
    return { x0, y0, x1, y1 };
  }

  function viewportRect(rect: PdfRect): {
    left: number;
    top: number;
    width: number;
    height: number;
  } {
    const pageHeight = pageSize.height / scale;
    const left = rect.x0 * scale;
    const width = (rect.x1 - rect.x0) * scale;
    const top = (pageHeight - rect.y1) * scale;
    const height = (rect.y1 - rect.y0) * scale;
    return { left, top, width, height };
  }

  return (
    <div className="space-y-2" ref={containerRef}>
      {loading ? (
        <p role="status" className="text-sm text-slate-600">
          Loading PDF preview…
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      ) : null}
      <div
        className="relative inline-block max-w-full overflow-auto rounded border bg-slate-100"
        aria-label="PDF draw surface"
        onPointerDown={(event) => {
          if (!drawMode) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          dragStart.current = { x: event.clientX, y: event.clientY };
          setDraft(null);
        }}
        onPointerMove={(event) => {
          if (!drawMode || !dragStart.current) return;
          const rect = toPdfRect(
            dragStart.current.x,
            dragStart.current.y,
            event.clientX,
            event.clientY,
          );
          setDraft(rect);
        }}
        onPointerUp={(event) => {
          if (!drawMode || !dragStart.current) return;
          const rect = toPdfRect(
            dragStart.current.x,
            dragStart.current.y,
            event.clientX,
            event.clientY,
          );
          dragStart.current = null;
          setDraft(null);
          if (rect) onManualRect(pageNumber, rect);
        }}
        onPointerCancel={() => {
          dragStart.current = null;
          setDraft(null);
        }}
      >
        <canvas ref={canvasRef} aria-label={`PDF page ${pageNumber}`} className="block" />
        <div className="pointer-events-none absolute inset-0">
          {pageEntities.map((entity) =>
            entity.rectangles.map((rect, index) => {
              const box = viewportRect(rect);
              return (
                <button
                  key={`${entity.id}-${index}`}
                  type="button"
                  // While drawing a manual region, keep overlays non-interactive so
                  // drag gestures reach the page surface instead of detection buttons.
                  className={`absolute border-2 ${overlayClass(entity, entity.id === selectedId)} ${
                    drawMode ? "pointer-events-none" : "pointer-events-auto"
                  }`}
                  style={{
                    left: box.left,
                    top: box.top,
                    width: box.width,
                    height: box.height,
                  }}
                  aria-label={`Detection ${entity.entity_type} on page ${pageNumber}`}
                  onClick={() => onSelectEntity(entity.id)}
                />
              );
            }),
          )}
          {draft ? (
            <div
              className="absolute border-2 border-dashed border-amber-600 bg-amber-300/30"
              style={(() => {
                const box = viewportRect(draft);
                return {
                  left: box.left,
                  top: box.top,
                  width: box.width,
                  height: box.height,
                };
              })()}
            />
          ) : null}
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Page {pageNumber} of {pageCount || "…"} · Zoom {(scale * 100).toFixed(0)}%
        {drawMode ? " · Draw a rectangle to add a manual redaction" : ""}
      </p>
    </div>
  );
}

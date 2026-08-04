"use client";

import { useMemo, useReducer, useRef, useState, type FormEvent, type ReactNode } from "react";

import { analyzeText, anonymizeText, MAX_TEXT_LENGTH } from "@/lib/api";
import { selectionToSourceOffsets } from "@/lib/selectionOffsets";
import { counts, createId, filterEntities, initialReviewState, reviewReducer } from "./reviewState";
import type { AnonymizationMethod, ReviewEntity } from "./types";
import { ENTITY_TYPES } from "./types";

const EXAMPLE =
  "Fictional User can be reached at fictional.user@example.com or 902-555-0182. " +
  "Mailing address uses postal code B3H 1Y2.";

const METHODS: AnonymizationMethod[] = ["replacement", "redaction", "masking", "pseudonymize"];

export function TextReviewWorkspace() {
  const [state, dispatch] = useReducer(reviewReducer, initialReviewState);
  const [inputText, setInputText] = useState("");
  const [step, setStep] = useState<"input" | "review" | "result">("input");
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editType, setEditType] = useState("PERSON");
  const [editStart, setEditStart] = useState(0);
  const [editEnd, setEditEnd] = useState(0);
  const previewRef = useRef<HTMLParagraphElement>(null);

  const visible = useMemo(() => filterEntities(state), [state]);
  const summary = useMemo(() => counts(state.entities), [state.entities]);

  async function onAnalyze(event: FormEvent) {
    event.preventDefault();
    dispatch({ type: "SET_ERROR", error: null });
    if (!inputText.trim()) {
      dispatch({ type: "SET_ERROR", error: "Provide non-empty text to analyze." });
      return;
    }
    if (inputText.length > MAX_TEXT_LENGTH) {
      dispatch({
        type: "SET_ERROR",
        error: `Text exceeds the maximum length of ${MAX_TEXT_LENGTH} characters.`,
      });
      return;
    }
    setLoading(true);
    try {
      const result = await analyzeText(inputText);
      dispatch({ type: "LOAD_ANALYSIS", text: result.text, detections: result.entities });
      setStep("review");
      setSelectedId(null);
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Analysis request failed.",
      });
    } finally {
      setLoading(false);
    }
  }

  async function onAnonymize() {
    setLoading(true);
    dispatch({ type: "SET_ERROR", error: null });
    try {
      const result = await anonymizeText({
        text: state.originalText,
        default_method: state.defaultMethod,
        entities: state.entities.map((entity) => ({
          client_id: entity.id,
          entity_type: entity.entity_type,
          start: entity.start,
          end: entity.end,
          review_status: entity.review_status,
          anonymization_method: entity.anonymization_method,
          detection_source: entity.detection_source,
          confidence: entity.confidence,
          manually_added: entity.manually_added,
          checksum_valid: entity.checksum_valid ?? null,
        })),
      });
      dispatch({
        type: "SET_RESULT",
        anonymizedText: result.anonymized_text,
        stats: {
          transformed_count: result.transformed_count,
          rejected_count: result.rejected_count,
          method_counts: result.method_counts,
          warnings: result.warnings,
        },
      });
      setStep("result");
    } catch (err) {
      dispatch({
        type: "SET_ERROR",
        error: err instanceof Error ? err.message : "Anonymization request failed.",
      });
    } finally {
      setLoading(false);
    }
  }

  function addManualFromSelection() {
    const container = previewRef.current;
    if (!container) {
      dispatch({ type: "SET_ERROR", error: "Preview is not ready for selection." });
      return;
    }
    const offsets = selectionToSourceOffsets(container);
    if (!offsets) {
      dispatch({
        type: "SET_ERROR",
        error: "Select text in the preview to add a manual entity.",
      });
      return;
    }
    const { start, end } = offsets;
    if (end > state.originalText.length) {
      dispatch({
        type: "SET_ERROR",
        error: "Could not map the selection to the original text. Select within the preview.",
      });
      return;
    }
    const entity: ReviewEntity = {
      id: createId(),
      entity_type: editType,
      start,
      end,
      text: state.originalText.slice(start, end),
      confidence: null,
      detection_source: "manual",
      recognizer_name: "manual",
      review_status: "manually_added",
      anonymization_method: state.defaultMethod,
      manually_added: true,
    };
    dispatch({ type: "ADD_MANUAL", entity });
    setSelectedId(entity.id);
  }

  function beginEdit(entity: ReviewEntity) {
    setSelectedId(entity.id);
    setEditType(entity.entity_type);
    setEditStart(entity.start);
    setEditEnd(entity.end);
  }

  function downloadTextAudit() {
    const report = {
      schema_version: "1.0",
      source: { type: "pasted_text" },
      analysis: {
        detection_count: state.entities.length,
        entity_category_counts: Object.fromEntries(
          Object.entries(
            state.entities.reduce<Record<string, number>>((acc, entity) => {
              acc[entity.entity_type] = (acc[entity.entity_type] ?? 0) + 1;
              return acc;
            }, {}),
          ).sort(([a], [b]) => a.localeCompare(b)),
        ),
      },
      review: {
        accepted: state.entities.filter((e) => e.review_status === "accepted").length,
        rejected: state.entities.filter((e) => e.review_status === "rejected").length,
        edited: state.entities.filter((e) => e.review_status === "edited").length,
        manually_added: state.entities.filter((e) => e.review_status === "manually_added").length,
      },
      output: {
        artifact_type: "anonymized_text",
        method_counts: state.transformStats?.method_counts ?? {},
        transformed_count: state.transformStats?.transformed_count ?? 0,
        rejected_count: state.transformStats?.rejected_count ?? 0,
      },
      privacy: {
        raw_values_included: false,
        original_content_included: false,
        anonymized_text_included: false,
        pseudonym_mapping_included: false,
      },
      warnings: state.transformStats?.warnings ?? [],
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "anonymization-audit-report.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function copyResult() {
    if (!state.anonymizedText) return;
    await navigator.clipboard.writeText(state.anonymizedText);
  }

  function downloadResult() {
    if (!state.anonymizedText) return;
    const blob = new Blob([state.anonymizedText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "anonymized-text.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="space-y-6" aria-labelledby="workspace-heading">
      <div>
        <h2 id="workspace-heading" className="text-xl font-semibold">
          Text review workspace
        </h2>
        <p className="text-sm text-slate-600">
          Analyze → review → anonymize. Review state stays in the browser; the API never permanently
          stores pasted text.
        </p>
      </div>

      {step === "input" && (
        <form onSubmit={onAnalyze} className="space-y-3">
          <label htmlFor="workspace-text" className="block text-sm font-medium">
            Text to analyze
          </label>
          <textarea
            id="workspace-text"
            rows={8}
            value={inputText}
            onChange={(event) => setInputText(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white p-3 text-sm"
            placeholder={EXAMPLE}
          />
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {loading ? "Analyzing…" : "Analyze text"}
            </button>
            <button
              type="button"
              className="rounded-md border px-4 py-2 text-sm"
              onClick={() => setInputText(EXAMPLE)}
            >
              Load fictional example
            </button>
          </div>
        </form>
      )}

      {loading && (
        <div role="status" aria-live="polite" className="rounded-lg border p-3 text-sm">
          Working…
        </div>
      )}

      {state.error && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800"
        >
          {state.error}
        </div>
      )}

      {step === "review" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <h3 className="font-medium">Original text</h3>
            <p
              ref={previewRef}
              className="min-h-48 whitespace-pre-wrap rounded-lg border bg-white p-3 text-sm leading-relaxed"
              aria-label="Original text with highlighted detections"
            >
              {renderHighlights(state.originalText, state.entities)}
            </p>
            <div className="flex flex-wrap gap-2">
              <label className="text-sm" htmlFor="manual-type">
                Manual entity type
              </label>
              <select
                id="manual-type"
                className="rounded border px-2 py-1 text-sm"
                value={editType}
                onChange={(event) => setEditType(event.target.value)}
              >
                {ENTITY_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="rounded-md border px-3 py-1 text-sm"
                onClick={addManualFromSelection}
              >
                Add manual entity from selection
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Pending detections are treated as accepted for anonymization until rejected. Rejected
              spans stay unchanged.
            </p>
          </div>

          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-medium">
                Detections ({summary.total}) · accepted-ish {summary.accepted} · rejected{" "}
                {summary.rejected}
              </h3>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="text-sm">
                Category
                <select
                  className="mt-1 w-full rounded border px-2 py-1"
                  value={state.categoryFilter}
                  onChange={(event) =>
                    dispatch({ type: "SET_FILTERS", categoryFilter: event.target.value })
                  }
                >
                  <option value="ALL">All</option>
                  {ENTITY_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                Min confidence
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  className="mt-1 w-full rounded border px-2 py-1"
                  value={state.confidenceThreshold}
                  onChange={(event) =>
                    dispatch({
                      type: "SET_FILTERS",
                      confidenceThreshold: Number(event.target.value),
                    })
                  }
                />
              </label>
              <label className="text-sm sm:col-span-2">
                Search
                <input
                  type="search"
                  className="mt-1 w-full rounded border px-2 py-1"
                  value={state.search}
                  onChange={(event) =>
                    dispatch({ type: "SET_FILTERS", search: event.target.value })
                  }
                />
              </label>
              <label className="text-sm sm:col-span-2">
                Default anonymization method
                <select
                  className="mt-1 w-full rounded border px-2 py-1"
                  value={state.defaultMethod}
                  onChange={(event) =>
                    dispatch({
                      type: "SET_DEFAULT_METHOD",
                      method: event.target.value as AnonymizationMethod,
                    })
                  }
                >
                  {METHODS.map((method) => (
                    <option key={method} value={method}>
                      {method}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-md border px-3 py-1 text-sm"
                onClick={() =>
                  dispatch({ type: "ACCEPT_VISIBLE", ids: visible.map((entity) => entity.id) })
                }
              >
                Accept visible
              </button>
              <button
                type="button"
                className="rounded-md border px-3 py-1 text-sm"
                onClick={() =>
                  dispatch({ type: "REJECT_VISIBLE", ids: visible.map((entity) => entity.id) })
                }
              >
                Reject visible
              </button>
              <button
                type="button"
                className="rounded-md bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50"
                disabled={loading}
                onClick={onAnonymize}
              >
                Generate anonymized text
              </button>
            </div>

            {visible.length === 0 ? (
              <p role="status" className="rounded border bg-white p-3 text-sm">
                No detections match the current filters.
              </p>
            ) : (
              <ul className="max-h-[28rem] space-y-2 overflow-auto">
                {visible.map((entity) => (
                  <li
                    key={entity.id}
                    className={`rounded-lg border bg-white p-3 text-sm ${
                      selectedId === entity.id ? "border-slate-900" : "border-slate-200"
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2 font-medium">
                      <span>{entity.entity_type}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                        {entity.review_status}
                      </span>
                      <span className="text-slate-500">
                        {entity.confidence === null
                          ? "user-supplied"
                          : `${(entity.confidence * 100).toFixed(0)}%`}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-slate-700">{entity.text}</p>
                    <p className="text-xs text-slate-500">
                      {entity.detection_source} · {entity.start}–{entity.end}
                      {entity.checksum_valid === true
                        ? " · checksum valid"
                        : entity.checksum_valid === false
                          ? " · checksum invalid"
                          : ""}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded border px-2 py-0.5 text-xs"
                        onClick={() =>
                          dispatch({ type: "SET_STATUS", id: entity.id, status: "accepted" })
                        }
                      >
                        Accept
                      </button>
                      <button
                        type="button"
                        className="rounded border px-2 py-0.5 text-xs"
                        onClick={() =>
                          dispatch({ type: "SET_STATUS", id: entity.id, status: "rejected" })
                        }
                      >
                        Reject
                      </button>
                      {entity.review_status === "rejected" && (
                        <button
                          type="button"
                          className="rounded border px-2 py-0.5 text-xs"
                          onClick={() =>
                            dispatch({
                              type: "SET_STATUS",
                              id: entity.id,
                              status: entity.manually_added ? "manually_added" : "accepted",
                            })
                          }
                        >
                          Restore
                        </button>
                      )}
                      <button
                        type="button"
                        className="rounded border px-2 py-0.5 text-xs"
                        onClick={() => beginEdit(entity)}
                      >
                        Edit
                      </button>
                      {entity.manually_added && (
                        <button
                          type="button"
                          className="rounded border px-2 py-0.5 text-xs"
                          onClick={() => dispatch({ type: "DELETE_ENTITY", id: entity.id })}
                        >
                          Delete manual
                        </button>
                      )}
                      <label className="text-xs">
                        Method
                        <select
                          className="ml-1 rounded border px-1"
                          value={entity.anonymization_method}
                          onChange={(event) =>
                            dispatch({
                              type: "SET_ENTITY_METHOD",
                              id: entity.id,
                              method: event.target.value as AnonymizationMethod,
                            })
                          }
                        >
                          {METHODS.map((method) => (
                            <option key={method} value={method}>
                              {method}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {selectedId === entity.id && (
                      <div className="mt-3 space-y-2 rounded border border-dashed p-2">
                        <label className="block text-xs">
                          Type
                          <select
                            className="mt-1 w-full rounded border px-2 py-1"
                            value={editType}
                            onChange={(event) => setEditType(event.target.value)}
                          >
                            {ENTITY_TYPES.map((type) => (
                              <option key={type} value={type}>
                                {type}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          <label className="text-xs">
                            Start
                            <input
                              type="number"
                              className="mt-1 w-full rounded border px-2 py-1"
                              value={editStart}
                              onChange={(event) => setEditStart(Number(event.target.value))}
                            />
                          </label>
                          <label className="text-xs">
                            End
                            <input
                              type="number"
                              className="mt-1 w-full rounded border px-2 py-1"
                              value={editEnd}
                              onChange={(event) => setEditEnd(Number(event.target.value))}
                            />
                          </label>
                        </div>
                        <button
                          type="button"
                          className="rounded bg-slate-800 px-2 py-1 text-xs text-white"
                          onClick={() =>
                            dispatch({
                              type: "EDIT_ENTITY",
                              id: entity.id,
                              entity_type: editType,
                              start: editStart,
                              end: editEnd,
                            })
                          }
                        >
                          Save edit
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {step === "result" && state.anonymizedText && (
        <div className="space-y-3">
          <h3 className="font-medium">Anonymized preview</h3>
          <pre className="whitespace-pre-wrap rounded-lg border bg-white p-3 text-sm">
            {state.anonymizedText}
          </pre>
          {state.transformStats && (
            <p className="text-sm text-slate-600">
              Transformed {state.transformStats.transformed_count}, rejected{" "}
              {state.transformStats.rejected_count}. Methods:{" "}
              {Object.entries(state.transformStats.method_counts)
                .map(([method, count]) => `${method}=${count}`)
                .join(", ") || "none"}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-md border px-3 py-1 text-sm"
              onClick={copyResult}
            >
              Copy to clipboard
            </button>
            <button
              type="button"
              className="rounded-md border px-3 py-1 text-sm"
              onClick={downloadResult}
            >
              Download .txt
            </button>
            <button
              type="button"
              className="rounded-md border px-3 py-1 text-sm"
              onClick={downloadTextAudit}
            >
              Download audit report
            </button>
            <button
              type="button"
              className="rounded-md border px-3 py-1 text-sm"
              onClick={() => {
                dispatch({ type: "BACK_TO_REVIEW" });
                setStep("review");
              }}
            >
              Return to review
            </button>
            <button
              type="button"
              className="rounded-md border px-3 py-1 text-sm"
              onClick={() => {
                dispatch({ type: "CLEAR_ALL" });
                setInputText("");
                setStep("input");
              }}
            >
              Clear current text
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function renderHighlights(text: string, entities: ReviewEntity[]) {
  const sorted = [...entities].sort((a, b) => a.start - b.start);
  const parts: ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((entity, index) => {
    if (entity.start < cursor) return;
    if (entity.start > cursor) parts.push(text.slice(cursor, entity.start));
    const className =
      entity.review_status === "rejected"
        ? "bg-slate-100 text-slate-500 line-through"
        : entity.manually_added
          ? "bg-sky-200"
          : entity.review_status === "edited"
            ? "bg-violet-200"
            : entity.review_status === "accepted"
              ? "bg-emerald-200"
              : "bg-amber-200";
    parts.push(
      <mark
        key={`${entity.id}-${index}`}
        className={`rounded px-0.5 ${className}`}
        title={`${entity.entity_type} (${entity.review_status})`}
      >
        {text.slice(entity.start, entity.end)}
      </mark>,
    );
    cursor = entity.end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}

"use client";

import { useState } from "react";

import { DocumentWorkflow } from "@/features/upload/DocumentWorkflow";
import { TextReviewWorkspace } from "@/features/review/TextReviewWorkspace";

type WorkspaceMode = "text" | "upload";

export function HomeWorkspace() {
  const [mode, setMode] = useState<WorkspaceMode>("text");

  return (
    <section className="space-y-4" aria-labelledby="workspace-mode-heading">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <h2 id="workspace-mode-heading" className="text-xl font-semibold text-slate-900">
            Workspace
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Paste text for explainable detection and anonymization, or upload a PDF, PNG, JPG, or
            JPEG for coordinate-aware review and irreversible redaction.
          </p>
        </div>
        <div role="group" aria-label="Workspace mode" className="flex gap-2">
          <button
            type="button"
            aria-pressed={mode === "text"}
            className={`btn focus-ring ${
              mode === "text" ? "bg-slate-900 text-white" : "border border-slate-300 bg-white"
            }`}
            onClick={() => setMode("text")}
          >
            Pasted text
          </button>
          <button
            type="button"
            aria-pressed={mode === "upload"}
            className={`btn focus-ring ${
              mode === "upload" ? "bg-slate-900 text-white" : "border border-slate-300 bg-white"
            }`}
            onClick={() => setMode("upload")}
          >
            Document upload
          </button>
        </div>
      </div>

      {mode === "text" ? (
        <TextReviewWorkspace />
      ) : (
        <DocumentWorkflow onSwitchToText={() => setMode("text")} />
      )}
    </section>
  );
}

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
        <div>
          <h2 id="workspace-mode-heading" className="text-xl font-semibold">
            Workspace
          </h2>
          <p className="text-sm text-slate-600">
            Paste text for review and anonymization, or upload a PDF for text-based analysis and
            true redaction.
          </p>
        </div>
        <div role="group" aria-label="Workspace mode" className="flex gap-2">
          <button
            type="button"
            aria-pressed={mode === "text"}
            className={`rounded-md px-3 py-2 text-sm ${
              mode === "text" ? "bg-slate-900 text-white" : "border"
            }`}
            onClick={() => setMode("text")}
          >
            Pasted text
          </button>
          <button
            type="button"
            aria-pressed={mode === "upload"}
            className={`rounded-md px-3 py-2 text-sm ${
              mode === "upload" ? "bg-slate-900 text-white" : "border"
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

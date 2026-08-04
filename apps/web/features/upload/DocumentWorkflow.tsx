"use client";

import { useState } from "react";

import { DocumentUploadPanel } from "@/features/upload/DocumentUploadPanel";
import { ImageReviewWorkspace } from "@/features/image/ImageReviewWorkspace";
import { PdfReviewWorkspace } from "@/features/pdf/PdfReviewWorkspace";
import type { JobMetadata } from "@/lib/api";

type DocumentWorkflowProps = {
  onSwitchToText: () => void;
};

export function DocumentWorkflow({ onSwitchToText }: DocumentWorkflowProps) {
  const [activeJob, setActiveJob] = useState<JobMetadata | null>(null);
  const [reviewing, setReviewing] = useState(false);

  if (reviewing && activeJob?.file_type === "pdf") {
    return (
      <PdfReviewWorkspace
        job={activeJob}
        onBack={() => setReviewing(false)}
        onDeleted={() => {
          setActiveJob(null);
          setReviewing(false);
        }}
      />
    );
  }

  if (reviewing && activeJob && (activeJob.file_type === "png" || activeJob.file_type === "jpeg")) {
    return (
      <ImageReviewWorkspace
        job={activeJob}
        onBack={() => setReviewing(false)}
        onDeleted={() => {
          setActiveJob(null);
          setReviewing(false);
        }}
      />
    );
  }

  return (
    <DocumentUploadPanel
      onSwitchToText={onSwitchToText}
      onJobReady={(job) => {
        setActiveJob(job);
      }}
      onAnalyzePdf={(job) => {
        setActiveJob(job);
        setReviewing(true);
      }}
      onOpenImageReview={(job) => {
        setActiveJob(job);
        setReviewing(true);
      }}
      activeJob={activeJob}
    />
  );
}

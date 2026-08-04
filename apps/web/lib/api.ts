export type HealthResponse = {
  status: "ok" | "degraded";
  database: "connected" | "unavailable";
  version: string;
};

export type DetectedEntity = {
  entity_type: string;
  start: number;
  end: number;
  text: string;
  confidence: number;
  detection_source: string;
  recognizer_name: string;
  checksum_valid?: boolean | null;
  normalized_value?: string | null;
  explanation?: string;
  overlap_resolution?: string;
};

export type AnalyzeTextResponse = {
  text: string;
  language: string;
  detection_count: number;
  entities: DetectedEntity[];
};

export type ReviewedEntityPayload = {
  client_id: string;
  entity_type: string;
  start: number;
  end: number;
  review_status: string;
  anonymization_method?: string;
  detection_source?: string;
  confidence?: number | null;
  manually_added?: boolean;
  checksum_valid?: boolean | null;
};

export type AnonymizeTextRequest = {
  text: string;
  entities: ReviewedEntityPayload[];
  default_method: string;
  language?: string;
};

export type AnonymizeTextResponse = {
  anonymized_text: string;
  transformed_count: number;
  rejected_count: number;
  skipped_count: number;
  method_counts: Record<string, number>;
  warnings: string[];
};

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
};

export type ApiError = Error & {
  code?: string;
  requestId?: string;
};

export type JobMetadata = {
  job_id: string;
  status: string;
  file_type: string;
  byte_size: number;
  page_count?: number | null;
  image_width?: number | null;
  image_height?: number | null;
  created_at: string;
  expires_at: string;
  error_code?: string | null;
};

export type DeleteJobResponse = {
  job_id: string;
  deleted: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const MAX_TEXT_LENGTH = 50000;
/** Must match backend MAX_UPLOAD_BYTES default (20 MiB). */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const ACCEPTED_UPLOAD_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"] as const;
export const ACCEPTED_UPLOAD_ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

async function readApiError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    const error = new Error(body.error?.message ?? fallback) as ApiError;
    error.code = body.error?.code;
    error.requestId = body.error?.request_id;
    return error;
  } catch {
    return new Error(fallback) as ApiError;
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/api/v1/health`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Health check request failed.");
  }
  return response.json() as Promise<HealthResponse>;
}

export async function analyzeText(text: string, language = "en"): Promise<AnalyzeTextResponse> {
  const response = await fetch(`${API_BASE}/api/v1/analyze/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language }),
  });
  if (!response.ok) {
    throw await readApiError(response, "Analysis request failed.");
  }
  return response.json() as Promise<AnalyzeTextResponse>;
}

export async function anonymizeText(payload: AnonymizeTextRequest): Promise<AnonymizeTextResponse> {
  const response = await fetch(`${API_BASE}/api/v1/anonymize/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await readApiError(response, "Anonymization request failed.");
  }
  return response.json() as Promise<AnonymizeTextResponse>;
}

export async function uploadDocument(file: File): Promise<JobMetadata> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/v1/documents`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw await readApiError(response, "Document upload failed.");
  }
  return response.json() as Promise<JobMetadata>;
}

export async function fetchJob(jobId: string): Promise<JobMetadata> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw await readApiError(response, "Job lookup failed.");
  }
  return response.json() as Promise<JobMetadata>;
}

export async function deleteJob(jobId: string): Promise<DeleteJobResponse> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw await readApiError(response, "Job deletion failed.");
  }
  return response.json() as Promise<DeleteJobResponse>;
}

export type PdfRect = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export type DocumentEntity = {
  id: string;
  entity_type: string;
  confidence: number | null;
  detection_source: string;
  recognizer_name: string;
  checksum_valid?: boolean | null;
  start: number;
  end: number;
  text: string | null;
  page_number: number;
  rectangles: PdfRect[];
  review_status: string;
  anonymization_method: string;
  manually_added: boolean;
  edited: boolean;
  source_kind?: string;
  ocr_confidence?: number | null;
  low_ocr_confidence?: boolean;
  preprocessing_used?: boolean;
  coordinate_space?: string;
};

export type AnalysisCoverage = {
  total_pages: number;
  embedded_text_pages: number;
  ocr_pages: number;
  failed_pages: number[];
  fully_analyzed: boolean;
  preprocessing_used: boolean;
  low_confidence_page_count: number;
  image_width?: number | null;
  image_height?: number | null;
  average_ocr_confidence?: number | null;
  low_confidence_warning?: boolean;
};

export type AnalyzeDocumentResponse = {
  job_id: string;
  status: string;
  page_count: number;
  pages_with_text: number;
  pages_needing_ocr: number[];
  detection_count: number;
  warning_code?: string | null;
  warning_message?: string | null;
  entities: DocumentEntity[];
  coverage?: AnalysisCoverage | null;
};

export type ArtifactMetadata = {
  artifact_id: string;
  job_id: string;
  artifact_type: string;
  byte_size: number;
  created_at: string;
  expires_at: string;
};

export type AnonymizeDocumentResponse = {
  job_id: string;
  status: string;
  artifact: ArtifactMetadata;
  redacted_count: number;
  rejected_count: number;
  warnings: string[];
};

export async function analyzeDocument(jobId: string): Promise<AnalyzeDocumentResponse> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/analyze`, {
    method: "POST",
  });
  if (!response.ok) {
    throw await readApiError(response, "Document analysis failed.");
  }
  return response.json() as Promise<AnalyzeDocumentResponse>;
}

export async function fetchDocumentEntities(
  jobId: string,
): Promise<{ entities: DocumentEntity[] }> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/entities`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw await readApiError(response, "Failed to load entities.");
  }
  return response.json() as Promise<{ entities: DocumentEntity[] }>;
}

export async function patchDocumentEntity(
  jobId: string,
  entityId: string,
  patch: Partial<{
    review_status: string;
    entity_type: string;
    anonymization_method: string;
    rectangles: PdfRect[];
    page_number: number;
  }>,
): Promise<DocumentEntity> {
  const response = await fetch(
    `${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/entities/${encodeURIComponent(entityId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  if (!response.ok) {
    throw await readApiError(response, "Failed to update entity.");
  }
  return response.json() as Promise<DocumentEntity>;
}

export async function createManualRedaction(
  jobId: string,
  payload: { page_number: number; rectangle: PdfRect; entity_type?: string },
): Promise<DocumentEntity> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/entities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await readApiError(response, "Failed to create manual redaction.");
  }
  return response.json() as Promise<DocumentEntity>;
}

export async function deleteDocumentEntity(jobId: string, entityId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/entities/${encodeURIComponent(entityId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    throw await readApiError(response, "Failed to delete entity.");
  }
}

export async function anonymizeDocument(
  jobId: string,
  body: { default_method?: string } = {},
): Promise<AnonymizeDocumentResponse> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/anonymize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_method: "redaction", ...body }),
  });
  if (!response.ok) {
    throw await readApiError(response, "Document redaction failed.");
  }
  return response.json() as Promise<AnonymizeDocumentResponse>;
}

export function jobSourcePdfUrl(jobId: string): string {
  return `${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/file`;
}

export function artifactDownloadUrl(jobId: string, artifactId: string): string {
  return `${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}`;
}

export type JobResultSummary = {
  job_id: string;
  status: string;
  source_type: string;
  output_type?: string | null;
  detection_count: number;
  review_status_counts: Record<string, number>;
  entity_category_counts: Record<string, number>;
  method_counts: Record<string, number>;
  analysis_coverage?: Record<string, unknown> | null;
  verification_status?: string | null;
  warnings: string[];
  artifact?: {
    artifact_id: string;
    artifact_type: string;
    byte_size: number;
    created_at: string;
    expires_at: string;
  } | null;
  created_at: string;
  expires_at: string;
  low_confidence_count: number;
  ocr_used: boolean;
  page_count?: number | null;
};

export async function fetchJobResult(jobId: string): Promise<JobResultSummary> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/result`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw await readApiError(response, "Failed to load job result.");
  }
  return response.json() as Promise<JobResultSummary>;
}

export function auditReportUrl(jobId: string): string {
  return `${API_BASE}/api/v1/jobs/${encodeURIComponent(jobId)}/audit-report`;
}

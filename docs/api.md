# API Reference — Intelligent PII Anonymization Platform

Base path: `/api/v1`.

All error responses use:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable safe message.",
    "request_id": "uuid"
  }
}
```

Responses include the `X-Request-ID` header.

---

## Implemented

### `GET /api/v1/health`

Returns API and database connectivity status. Does not expose secrets, connection
strings, stack traces, or environment details.

**Response (200):**

```json
{
  "status": "ok",
  "database": "connected",
  "version": "0.1.0"
}
```

When the database is unavailable, `status` is `degraded` and `database` is
`unavailable`.

---

### `POST /api/v1/analyze/text`

Analyze pasted text with the hybrid PII detection pipeline (regex → checksum →
Presidio → spaCy → normalization → overlap resolution).

#### Request

```json
{
  "text": "Fictional User can be reached at fictional.user@example.com.",
  "language": "en"
}
```

| Field | Type | Rules |
|-------|------|-------|
| `text` | string | Required; non-empty after trim; max length configurable (`MAX_TEXT_LENGTH`, default 50000) |
| `language` | string | Optional; default `en` |

#### Response (200)

```json
{
  "text": "Fictional User can be reached at fictional.user@example.com.",
  "language": "en",
  "detection_count": 2,
  "entities": [
    {
      "entity_type": "PERSON",
      "start": 0,
      "end": 14,
      "text": "Fictional User",
      "confidence": 0.85,
      "detection_source": "spacy",
      "recognizer_name": "presidio_person",
      "checksum_valid": null,
      "normalized_value": null,
      "explanation": "Detected by Presidio/spaCy as PERSON",
      "overlap_resolution": "selected"
    },
    {
      "entity_type": "EMAIL_ADDRESS",
      "start": 34,
      "end": 60,
      "text": "fictional.user@example.com",
      "confidence": 0.95,
      "detection_source": "regex",
      "recognizer_name": "regex_email",
      "checksum_valid": null,
      "normalized_value": "fictional.user@example.com",
      "explanation": "Matched email pattern",
      "overlap_resolution": "selected"
    }
  ]
}
```

The response may echo the submitted text to the client for highlighting. That text is
**never** written to application logs, the database, telemetry, or persistent storage.

#### Validation errors

| Code | Status | When |
|------|--------|------|
| `EMPTY_TEXT` | 400 | Empty or whitespace-only text |
| `TEXT_TOO_LONG` | 400 | Exceeds `MAX_TEXT_LENGTH` |
| `SPACY_MODEL_MISSING` | 500 | Model not installed at startup |
| `NLP_DEPENDENCY_MISSING` | 500 | Presidio/spaCy packages missing |

#### Privacy limitations

- Logs record request ID, text length, duration, detection counts, and category counts only.
- Detected values, names, emails, phones, SINs, cards, and raw text are never logged.
- Format recognition is not proof that an identifier is genuine.

#### Detection limitations

- Automated detection can produce false positives or miss sensitive information.
- Street addresses, dates of birth, and medical identifiers use conservative patterns.
- Canadian bank transit/institution/account matching requires labeled fields and does not
  establish that an account is real.
- spaCy NER quality depends on `en_core_web_sm` (not production-grade accuracy claims).

---

### `POST /api/v1/anonymize/text`

Stateless text anonymization after human review. The browser holds review state; the
server validates spans, resolves review overlaps, transforms accepted entities, and
discards all sensitive data when the request ends. No PostgreSQL persistence of text,
detections, or pseudonym mappings.

#### Request

```json
{
  "text": "Fictional User at fictional.user@example.com phone 902-555-0182",
  "default_method": "replacement",
  "language": "en",
  "entities": [
    {
      "client_id": "e1",
      "entity_type": "EMAIL_ADDRESS",
      "start": 18,
      "end": 44,
      "review_status": "accepted",
      "anonymization_method": "masking",
      "detection_source": "regex",
      "confidence": 0.95,
      "manually_added": false
    },
    {
      "client_id": "e2",
      "entity_type": "PHONE_NUMBER",
      "start": 51,
      "end": 63,
      "review_status": "rejected",
      "anonymization_method": "replacement",
      "detection_source": "regex",
      "confidence": 0.88,
      "manually_added": false
    }
  ]
}
```

Client-supplied entity substrings are ignored. The server derives text from validated
`start`/`end` offsets.

#### Review statuses

`pending`, `accepted`, `rejected`, `edited`, `manually_added`

Pending, accepted, edited, and manually_added entities are transformed. Rejected entities
are never transformed.

#### Anonymization methods

| Method | Behavior |
|--------|----------|
| `replacement` | `<ENTITY_TYPE>` labels |
| `redaction` | Block characters `█` matching Unicode span length |
| `masking` | Entity-aware partial masks (email/phone/card/SIN/postal/IP/URL/…) |
| `pseudonymize` | Request-scoped consistent fictional replacements |

#### Masking rules (summary)

- Email: keep first local character + domain (`f********@example.com`)
- Phone: keep last four digits (`***-***-0182`)
- Credit card: keep last four digits
- SIN: keep last three digits
- Postal: conservative `*** **Y2`-style mask
- IP: keep first octet only
- URL: keep scheme+host, drop path/query
- Names: first letter + stars per token
- Fallback: conservative first/last character mask for short values

#### Pseudonymization

Same normalized value + entity type → same pseudonym within one request. Different values
do not collide. Mappings are discarded after the request and never logged or stored.

#### Overlap after review

Manual / edited outrank automatic. Exact duplicates merge. Conflicting overlapping manual
or edited entities return `CONFLICTING_MANUAL_ENTITIES`. Replacements apply right-to-left.

#### Response (200)

```json
{
  "anonymized_text": "Fictional User at f********@example.com phone 902-555-0182",
  "transformed_count": 1,
  "rejected_count": 1,
  "skipped_count": 0,
  "method_counts": { "masking": 1 },
  "warnings": []
}
```

Does not return original text, detected values, or pseudonym mappings.

#### Validation errors

| Code | Status | When |
|------|--------|------|
| `EMPTY_TEXT` | 400 | Empty text |
| `TEXT_TOO_LONG` | 400 | Exceeds max length |
| `INVALID_ENTITY_SPAN` | 400 | Negative/empty/out-of-range offsets |
| `UNSUPPORTED_ENTITY_TYPE` | 400 | Unknown type |
| `INVALID_REVIEW_STATUS` | 400 | Unknown status |
| `UNSUPPORTED_ANONYMIZATION_METHOD` | 400 | Unknown method |
| `CONFLICTING_MANUAL_ENTITIES` | 400 | Overlapping manual/edited spans |

#### Privacy limitations

- Logs: request ID, lengths, counts, method counts, duration, status — never text or values.
- No durable storage of pasted text or mappings in Phase 3.

---

### `POST /api/v1/documents`

Secure multipart upload for temporary document storage (Phase 4). Validates extension,
declared MIME type, file signature, and document structure. Does **not** extract text,
run OCR, detect PII, or anonymize documents.

#### Request

`multipart/form-data` with a single `file` field.

Supported types:

| Extension | MIME | Signature |
|-----------|------|-----------|
| `.pdf` | `application/pdf` | `%PDF` |
| `.png` | `image/png` | PNG magic |
| `.jpg` / `.jpeg` | `image/jpeg` | JPEG SOI |

#### Response (201)

```json
{
  "job_id": "11111111-1111-1111-1111-111111111111",
  "status": "pending",
  "file_type": "pdf",
  "byte_size": 2048,
  "page_count": 1,
  "image_width": null,
  "image_height": null,
  "created_at": "2026-08-03T12:00:00Z",
  "expires_at": "2026-08-03T13:00:00Z",
  "error_code": null
}
```

Does **not** return storage paths, storage keys, original filenames, file contents, or hashes.

#### Common error codes

| Code | Status |
|------|--------|
| `EMPTY_FILE` | 400 |
| `UNSUPPORTED_FILE_TYPE` | 400 |
| `FILE_TOO_LARGE` | 413 |
| `MIME_TYPE_MISMATCH` | 400 |
| `FILE_SIGNATURE_MISMATCH` | 400 |
| `EXECUTABLE_CONTENT_REJECTED` | 400 |
| `ARCHIVE_CONTENT_REJECTED` | 400 |
| `CORRUPT_PDF` | 400 |
| `PASSWORD_PROTECTED_PDF` | 400 |
| `PDF_PAGE_LIMIT_EXCEEDED` | 400 |
| `EMPTY_PDF` | 400 |
| `CORRUPT_IMAGE` | 400 |
| `IMAGE_FORMAT_MISMATCH` | 400 |
| `IMAGE_PIXEL_LIMIT_EXCEEDED` | 400 |
| `INVALID_IMAGE_DIMENSIONS` | 400 |
| `STORAGE_FAILURE` | 500 |

---

### `GET /api/v1/jobs/{job_id}`

Returns safe ProcessingJob metadata. Returns `JOB_NOT_FOUND` (404) or `JOB_EXPIRED` (410).

### `DELETE /api/v1/jobs/{job_id}`

Immediately deletes the temporary file, generated artifacts, and database metadata.
Path is never derived from user input. Returns `{ "job_id": "...", "deleted": true }`.
Unknown jobs return `JOB_NOT_FOUND`.

---

### Phase 5 — text-based PDF workflow

#### `POST /api/v1/jobs/{job_id}/analyze`

Extracts embedded PDF text with coordinates, runs the Phase 2 detection pipeline, maps
offsets to rectangles, and persists entity metadata **without** detected values.

Image-only / insufficient-text PDFs return `OCR_REQUIRED` (422). Mixed documents may
include `warning_code: PARTIAL_TEXT_EXTRACTION`.

#### `GET /api/v1/jobs/{job_id}/entities`

Lists entities. Text shown for review is re-derived from a fresh extraction; it is not
stored in the database.

#### `PATCH /api/v1/jobs/{job_id}/entities/{entity_id}`

Update review status, type, or rectangles. PDF anonymization method is **redaction only**.

#### `POST /api/v1/jobs/{job_id}/entities`

Create a manual rectangular redaction (`page_number` + `rectangle` in PDF user space).

#### `DELETE /api/v1/jobs/{job_id}/entities/{entity_id}`

Delete a manually added region only.

#### `POST /api/v1/jobs/{job_id}/anonymize`

Applies true PyMuPDF redactions to a **new** file, verifies sensitive substrings are gone,
persists `GeneratedArtifact` metadata, returns nested `artifact` object.

#### `GET /api/v1/jobs/{job_id}/file`

Streams the original stored PDF for preview (`inline`, filename `anonymized-source.pdf`).

#### `GET /api/v1/jobs/{job_id}/artifacts/{artifact_id}`

Downloads the redacted PDF (`attachment`, filename `anonymized-document.pdf`).

### Additional Phase 5 error codes

| Code | When |
|------|------|
| `OCR_REQUIRED` | Scanned PDF when OCR is disabled/unavailable |
| `OCR_DISABLED` / `OCR_ENGINE_UNAVAILABLE` / `OCR_TIMEOUT` / `OCR_FAILED` | OCR engine issues |
| `OCR_PAGE_LIMIT_EXCEEDED` | Synchronous OCR page budget exceeded |
| `OCR_NO_TEXT` | Image OCR found no readable text |
| `OCR_COORDINATE_MAPPING_FAILED` / `INVALID_OCR_COORDINATES` | Mapping failures |
| `PDF_RENDER_FAILED` / `PREPROCESSING_FAILED` | Render/preprocess failures |
| `IMAGE_ANALYSIS_FAILED` / `IMAGE_REDACTION_FAILED` | Image pipeline failures |
| `OUTPUT_VERIFICATION_FAILED` | Post-redaction verification failed |
| `PARTIAL_TEXT_EXTRACTION` / `PARTIAL_ANALYSIS` | Warnings: incomplete coverage |
| `PDF_EXTRACTION_FAILED` | Extraction failure |
| `DOCUMENT_ANALYSIS_FAILED` | Analysis failure |
| `ENTITY_MAPPING_FAILED` | Offset→coordinate mapping failed |
| `INVALID_MANUAL_REDACTION` | Bad manual rectangle |
| `REDACTION_FAILED` | Redaction apply failure |
| `REDACTION_VERIFICATION_FAILED` | Post-redaction text still present |
| `ARTIFACT_NOT_FOUND` / `ARTIFACT_EXPIRED` | Artifact access |

Analyze responses may include safe `coverage` metadata (`fully_analyzed`, `ocr_pages`,
`failed_pages`, `average_ocr_confidence`, …) and never include OCR text, storage keys, or
paths. Entity responses may include `source_kind`, `ocr_confidence`, `low_ocr_confidence`,
`preprocessing_used`, and `coordinate_space`.

Artifact downloads:

| Artifact type | Filename | MIME |
|---------------|----------|------|
| `redacted_pdf` | `anonymized-document.pdf` | `application/pdf` |
| `redacted_png` | `anonymized-image.png` | `image/png` |
| `redacted_jpeg` | `anonymized-image.jpg` | `image/jpeg` |

Download headers include `X-Content-Type-Options: nosniff` and
`Cache-Control: no-store, private`.

---

## Phase 7 — Results and audit reports

### `GET /api/v1/jobs/{job_id}/result`

Safe result summary for a completed (or in-progress) document job. Never returns
source contents, detected values, OCR/extracted text, storage keys, paths, or
original filenames.

**Response (200) fields:** `job_id`, `status`, `source_type`, `output_type`,
`detection_count`, `review_status_counts`, `entity_category_counts`,
`method_counts`, `analysis_coverage`, `verification_status`, `warnings`,
`artifact` (safe metadata only), `created_at`, `expires_at`,
`low_confidence_count`, `ocr_used`, `page_count`.

### `GET /api/v1/jobs/{job_id}/audit-report`

Downloads a versioned JSON audit report (`schema_version: "1.0"`) as
`anonymization-audit-report.json` with `application/json`, `nosniff`, and
`Cache-Control: no-store, private`.

Generated dynamically from persisted safe metadata only. **No `AuditEvent` table**
was added — `ProcessingJob`, `DetectedEntity`, and `GeneratedArtifact` already
provide the required counts and coverage.

Excluded from the report: original/OCR/extracted text, detected values,
pseudonym mappings, filenames, paths, storage keys, EXIF/GPS, raw recognizer
output, and full exception messages.

Example (fictional):

```json
{
  "schema_version": "1.0",
  "job_id": "00000000-0000-4000-8000-000000000001",
  "source": {
    "type": "pdf",
    "validated_format": "application/pdf",
    "byte_size": 12345,
    "page_count": 2
  },
  "analysis": {
    "status": "completed",
    "detection_count": 5,
    "entity_category_counts": {
      "EMAIL_ADDRESS": 2,
      "PERSON": 2,
      "PHONE_NUMBER": 1
    },
    "embedded_text_pages": 1,
    "ocr_pages": 1,
    "failed_pages": 0,
    "fully_analyzed": true,
    "low_confidence_count": 1,
    "preprocessing_used": false
  },
  "review": {
    "accepted": 3,
    "rejected": 1,
    "edited": 0,
    "manually_added": 1,
    "pending": 0
  },
  "output": {
    "artifact_type": "redacted_pdf",
    "verification_status": "passed",
    "method_counts": { "redaction": 4 },
    "byte_size": 11111
  },
  "privacy": {
    "raw_values_included": false,
    "original_content_included": false,
    "pseudonym_mapping_included": false
  },
  "created_at": "2026-08-03T12:00:00+00:00",
  "expires_at": "2026-08-03T13:00:00+00:00",
  "warnings": []
}
```

Pasted-text workflows remain stateless: the browser may download a **client-generated**
safe audit JSON without raw values; there is no persistent text job history.

### Delete-now and expiration

`DELETE /api/v1/jobs/{job_id}` removes the source upload, artifacts, OCR work files,
entity rows, artifact rows, and the job row. Subsequent result/audit/artifact/preview
calls return not-found. Expired jobs return `JOB_EXPIRED` (410) for result and audit
access. Cleanup is single-instance in-process (MVP limitation).

---

## Phase 4/6/7 limits (defaults)

| Setting | Default |
|---------|---------|
| `MAX_UPLOAD_BYTES` | 20971520 (20 MiB) |
| `MAX_PDF_PAGES` | 50 |
| `MAX_IMAGE_PIXELS` | 40000000 |
| `UPLOAD_TTL_MINUTES` | 60 |
| `UPLOAD_CLEANUP_INTERVAL_SECONDS` | 300 |
| `TEMP_UPLOAD_DIR` | `/var/pii-uploads` (Docker) |
| `OCR_LANGUAGE` | `eng` |
| `OCR_TIMEOUT_SECONDS` | 60 |
| `OCR_RENDER_DPI` | 200 |
| `OCR_MAX_PAGES` | 20 (capped by `MAX_PDF_PAGES`) |
| `OCR_TEMP_DIR` | `/var/pii-uploads/ocr-work` |

Signature checks reduce risk but are **not** a substitute for malware scanning.

In-process cleanup assumes a single API instance. Synchronous OCR is intentionally
bounded by `OCR_MAX_PAGES`.

---

## Planned

| Method | Path | Phase |
|--------|------|-------|
| Auth / history / RBAC | — | 8+ (out of scope for Phase 7) |

Phase 7 results and audit reports are implemented. Phase 8 security hardening and
portfolio polish are not started.

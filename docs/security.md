# Security — Intelligent PII Anonymization Platform

> Status: completed for Phase 8 (security hardening and testing). This document
> reflects the controls implemented through Phase 8 for a **local, single-instance,
> unauthenticated MVP**. It is not a claim of production readiness. See
> [§14 Production requirements](#14-production-requirements-not-implemented-in-phase-8)
> for controls that a real deployment must add.

This document describes the platform's threat model, trust boundaries, and the
controls that protect uploaded documents and detected PII. It complements
[architecture.md](architecture.md) and [privacy.md](privacy.md).

**Guiding principle:** no control here *eliminates* risk. Each threat has a
documented **residual risk**. Defense-in-depth reduces likelihood and impact, but
this is a portfolio/demonstration system, not a hardened production service.

---

## 1. Assets

What an attacker (or a careless operator) could want to read, alter, or destroy:

| Asset | Sensitivity | Where it lives |
|-------|-------------|----------------|
| Uploaded source documents (PDF/PNG/JPEG) | High — may contain real PII | Temp upload volume (`api_uploads`), random keys |
| Pasted text and its detections | High | Request-scoped only; never persisted |
| Detected PII **values** | High | Never persisted; held in browser and in request memory |
| Detection **metadata** (type, offsets, rectangles, confidence, review status) | Medium | PostgreSQL `detected_entities` |
| Generated artifacts (redacted PDF/PNG/JPEG) | Medium — should be free of accepted PII, but user must verify | Temp upload volume |
| Job metadata (file type, size, page/pixel counts, timestamps, coverage JSON) | Low–Medium | PostgreSQL `processing_jobs` |
| OCR work files (rendered page rasters, pre-processed images) | High while present | `TEMP_UPLOAD_DIR/ocr-work`, random names, deleted after use |
| Structured logs | Low (by policy) | stdout / container logs |
| Configuration and DB credentials | High | `.env` (not committed), Compose env |

---

## 2. Trust boundaries

- **Untrusted:** the browser, the uploaded file bytes, all client-supplied
  headers (including `X-Request-ID` and `Host`), custom recognizer regex patterns,
  and any pasted text.
- **Semi-trusted / validated:** request bodies after Pydantic validation and
  after the file-validation pipeline.
- **Trusted:** the API process, the temp storage volume, and PostgreSQL — all on
  the Compose network, none published to the public internet in the MVP.

The API edge validates and enforces limits. Everything crossing the browser → API
boundary is treated as hostile until validated. The architecture trust-boundary
diagram is in [architecture.md](architecture.md#8-trust-boundaries).

**Boundary caveat:** there is **no authentication or authorization boundary**
between users. Any client that can reach the API can act on any job whose UUID it
knows. This is acceptable only because ports bind to `127.0.0.1` on the host and
the system is single-user by design (see §3, §7, §14).

---

## 3. Entry points

| Entry point | Surface | Notes |
|-------------|---------|-------|
| `POST /api/v1/analyze/text` | Pasted text, optional custom recognizers | Length-bounded; regex sandboxed |
| `POST /api/v1/anonymize/text` | Text + validated spans | Stateless; no persistence |
| `POST /api/v1/documents` | Multipart upload | Streamed to quarantine, full validation pipeline |
| `GET/DELETE /api/v1/jobs/{job_id}` | Job metadata / delete-now | UUID path param |
| `POST /api/v1/jobs/{job_id}/analyze` | Triggers extraction/OCR/detection | Per-job lock + concurrency slot |
| `GET/POST/PATCH/DELETE .../entities` | Entity review | Count/size bounded |
| `POST /api/v1/jobs/{job_id}/anonymize` | Redaction | Per-job lock + redaction slot |
| `GET .../file`, `.../artifacts/{id}` | Downloads | `no-store`, `nosniff` |
| `GET .../result`, `.../audit-report` | Safe summaries | Privacy assertion on payload |
| `GET /api/v1/health` | Liveness/DB check | No sensitive data |

Ports bind to `127.0.0.1:8000` (API) and `127.0.0.1:3000` (web). PostgreSQL is
**not** published to the host (`expose` only, on the Compose network). Interactive
API docs (`/docs`) are served only when `ENVIRONMENT=development`.

---

## 4. Attacker capabilities (assumptions)

We assume an attacker who can:

- Reach the API on `127.0.0.1` (i.e., a local user or process on the host).
- Craft arbitrary multipart uploads, headers, JSON bodies, and regex patterns.
- Supply malformed, oversized, or maliciously structured PDFs/images.
- Guess or observe job/artifact UUIDs (e.g., via browser history or shoulder-surfing).

We explicitly **do not** defend in Phase 8 against:

- A remote network attacker (no public exposure in the MVP; no TLS).
- A privileged host operator with root/Docker socket access.
- A supply-chain compromise of a pinned dependency that passes audit.
- A determined attacker with a Tesseract/PyMuPDF/Pillow 0-day (sandboxing is a
  production requirement, §14).

---

## 5. Sensitive data lifecycle

1. **Ingress** — text is held in request memory only; files are streamed in
   1 MiB chunks to a `.quarantine-<random>` file (never using the client filename).
2. **Validation** — signature/MIME/extension agreement, structural validation,
   active-content rejection (PDF), decode + pixel limits (image).
3. **Promotion** — validated file is atomically renamed to a random storage key
   (`<32 hex>.<ext>`) under `TEMP_UPLOAD_DIR`.
4. **Processing** — extraction/OCR/detection run in-process; OCR intermediates
   live under `ocr-work/` with random names.
5. **Review** — only detection *metadata* is persisted; **values are never stored**.
6. **Output** — redacted artifact is written, sanitized (metadata stripped), and
   verified by re-extraction/re-OCR.
7. **Egress** — downloads carry `Cache-Control: no-store, private` and `nosniff`.
8. **Deletion** — `DELETE` removes DB rows, source, artifacts, and OCR work;
   TTL cleanup + startup reconciliation remove expired/orphaned data.

**No pasted text, extracted text, OCR text, detected values, or pseudonym
mappings are ever written to PostgreSQL or logs.**

---

## 6. Threat model

Each threat below uses the structure: **Threat → Attack scenario → Existing
mitigation (Phases 1–7) → Phase 8 mitigation → Residual risk → Production
recommendation.**

### 6.1 File-upload risks (unsupported / disguised content)

- **Threat:** An attacker uploads an executable, archive, or otherwise unsupported
  file to trigger unsafe handling.
- **Attack scenario:** `evil.exe` renamed to `report.pdf`, or a ZIP bomb sent as
  `image.png`.
- **Existing mitigation:** Streaming size cap (`MAX_UPLOAD_BYTES`, 20 MiB);
  extension allow-list (`.pdf/.png/.jpg/.jpeg`); declared-MIME check; file-signature
  sniffing; extension/MIME/signature must **agree**; PE/ELF and ZIP/RAR/7z/GZIP
  rejected with `EXECUTABLE_CONTENT_REJECTED` / `ARCHIVE_CONTENT_REJECTED`.
- **Phase 8 mitigation:** Per-process upload concurrency slot (`MAX_CONCURRENT_UPLOADS`);
  safe error codes only; tests covering disguised executables and signature mismatch.
- **Residual risk:** Signature checks are **not malware scanning**. A file that is a
  structurally valid PDF/image but semantically malicious passes ingestion.
- **Production recommendation:** Integrate malware scanning (e.g., ClamAV) and/or a
  sandboxed conversion step; quarantine on scanner failure.

### 6.2 Malicious PDF

- **Threat:** A PDF with active content (JS, launch actions, embedded files) or a
  parser-exploiting structure.
- **Attack scenario:** PDF with `/OpenAction /JavaScript`, an embedded payload, or a
  crafted object stream targeting PyMuPDF.
- **Existing mitigation:** PyMuPDF structural validation — encryption, empty, and
  page-count checks (`MAX_PDF_PAGES`, 50); corruption → `CORRUPT_PDF`.
- **Phase 8 mitigation:** `reject_active_pdf_content` rejects embedded files
  (`EMBEDDED_FILE_REJECTED`), document JavaScript / named JS
  (`ACTIVE_PDF_CONTENT_REJECTED`), and unsafe annotations/actions —
  FileAttachment/Sound/Movie/Screen/RichMedia/Launch and action dictionaries
  containing `/JS`, `/Launch`, `/GoToR`, `/ImportData`, `/SubmitForm`,
  `/RichMedia`, `/EmbeddedFile`, `/Filespec` (`UNSAFE_PDF_ACTION_REJECTED`).
  Generated PDFs are additionally sanitized (see §7.9).
- **Residual risk:** Detection relies on what PyMuPDF surfaces; obfuscated or
  novel active-content constructs may not be enumerated. A PyMuPDF parser
  vulnerability would execute inside the API container. This is **not** a full PDF
  disarm/reconstruction.
- **Production recommendation:** Sandboxed parsing (seccomp/gVisor/microVM), a
  dedicated PDF sanitizer/CDR product, and continuous PyMuPDF patching.

### 6.3 Malicious image

- **Threat:** A decompression bomb or malformed image aiming to exhaust memory or
  crash the decoder.
- **Attack scenario:** A tiny PNG that decodes to billions of pixels, or a truncated
  JPEG that triggers unsafe decoder paths.
- **Existing mitigation:** Pillow decode with `LOAD_TRUNCATED_IMAGES = False`,
  format-match check, non-positive dimension rejection.
- **Phase 8 mitigation:** `Image.MAX_IMAGE_PIXELS` bounded by `MAX_IMAGE_PIXELS`
  (40M) with explicit `DecompressionBombError → IMAGE_PIXEL_LIMIT_EXCEEDED`;
  animated/multi-frame rejection (`UNSUPPORTED_IMAGE_FRAMES`); EXIF touched only
  defensively and stripped from outputs.
- **Residual risk:** A Pillow/libjpeg/zlib 0-day could still be reachable; the
  pixel cap is a heuristic, not a proof of safety.
- **Production recommendation:** Decode in a sandboxed, memory-limited worker;
  keep imaging libraries patched; consider re-encoding through a hardened pipeline.

### 6.4 OCR abuse / resource exhaustion via OCR

- **Threat:** An attacker forces expensive OCR to exhaust CPU/time.
- **Attack scenario:** A many-page scanned PDF or a maximum-pixel image submitted
  repeatedly to pin the OCR path.
- **Existing mitigation:** Tesseract invoked via **argv only (never `shell=True`)**
  with a hard `OCR_TIMEOUT_SECONDS` (60) that kills the process; English only;
  render DPI bounded (72–300); `OCR_MAX_PAGES` (effective = min with `MAX_PDF_PAGES`).
- **Phase 8 mitigation:** `MAX_CONCURRENT_OCR_JOBS` (2) semaphore; OCR text, TSV,
  work-file paths, and image bytes never logged; timeouts return `OCR_TIMEOUT`.
- **Residual risk:** OCR remains synchronous and single-instance; sustained
  submissions can still degrade responsiveness. Limits are per-process, not global.
- **Production recommendation:** Move OCR to a queue/worker pool with global rate
  limits and per-tenant quotas; autoscale; enforce backpressure.

### 6.5 Resource exhaustion (general DoS)

- **Threat:** Memory/CPU/disk exhaustion via large or numerous requests.
- **Attack scenario:** Parallel uploads, huge regex inputs, or many concurrent
  redactions.
- **Existing mitigation:** Text length cap (`MAX_TEXT_LENGTH`, 50k); upload size
  cap; page/pixel caps.
- **Phase 8 mitigation:** Bounded semaphores for uploads, document jobs, OCR, and
  redactions returning `RESOURCE_BUSY` (429, `Retry-After`); per-job locks
  returning `JOB_BUSY` (409); entity/rectangle/recognizer/pattern-length caps;
  regex timeout (`CUSTOM_REGEX_TIMEOUT_SECONDS`, 0.25s).
- **Residual risk:** No distributed or IP-based rate limiting; a local attacker can
  still submit within limits repeatedly. See §6.25.
- **Production recommendation:** Edge/API-gateway rate limiting, per-client quotas,
  request timeouts, and resource cgroups.

### 6.6 Path traversal

- **Threat:** Escaping the temp directory to read/write arbitrary paths.
- **Attack scenario:** A storage key like `../../etc/passwd` or a client filename
  used as a path.
- **Existing mitigation:** Client filenames are **never** used in filesystem paths;
  storage keys are server-generated (`<32 hex>.<ext>`).
- **Phase 8 mitigation:** `assert_valid_storage_key` rejects `/`, `\`, `..`, null
  bytes, absolute/UNC/drive-relative forms, and anything not matching the strict
  key regex; every resolved path is re-checked with `relative_to(base)`.
- **Residual risk:** Correctness depends on the containment checks; a logic
  regression could reintroduce traversal (mitigated by tests).
- **Production recommendation:** Keep containment tests in CI; consider a chrooted
  or object-store backend with no path semantics.

### 6.7 Symlink attacks

- **Threat:** A symlink in the temp directory redirects a write/delete to a
  sensitive location.
- **Attack scenario:** A pre-planted symlink at a storage-key name causing writes to
  follow the link.
- **Existing mitigation:** Path containment (§6.6).
- **Phase 8 mitigation:** Quarantine writes use `O_CREAT|O_EXCL` (+ `O_NOFOLLOW`
  where available); `os.lstat` + `S_ISLNK`/`S_ISREG` checks reject symlinks and
  non-regular files (`UNSAFE_STORAGE_PATH`); promotion refuses symlink sources or
  destinations; `safe_unlink` only unlinks the link itself or a regular file.
- **Residual risk:** On Windows, `O_NOFOLLOW` and POSIX modes are unavailable;
  symlink-specific tests **may be skipped** there, so coverage is platform-dependent.
- **Production recommendation:** Run on Linux with a dedicated, non-shared volume;
  restrict volume write access to the API UID only.

### 6.8 MIME spoofing

- **Threat:** A mismatched declared type bypasses validation.
- **Attack scenario:** `Content-Type: application/pdf` on PNG bytes, or vice versa.
- **Existing mitigation:** Declared MIME treated as an untrusted hint only.
- **Phase 8 mitigation:** Signature-derived type must equal the hint-derived type,
  else `FILE_SIGNATURE_MISMATCH`; structural validation then confirms the real
  format (`IMAGE_FORMAT_MISMATCH` on disagreement).
- **Residual risk:** Polyglot files valid as more than one type could satisfy one
  path; only the allow-listed types are ever processed.
- **Production recommendation:** Add content-defined type detection and re-encode
  outputs from a canonical decode.

### 6.9 Stored / reflected injection (XSS)

- **Threat:** Malicious content rendered in the UI or reflected in responses.
- **Attack scenario:** A filename or detected value containing `<script>` shown in
  the browser.
- **Existing mitigation:** Original filenames are never persisted or returned;
  detected values are not stored server-side; React escapes rendered strings.
- **Phase 8 mitigation:** API error messages are static, code-based strings that
  never echo request values; CSP on API responses is `default-src 'none'`.
- **Residual risk:** The web app is Next.js; its CSP requires `'unsafe-inline'` and
  `blob:` for the framework and PDF.js (see §7.10) — CSP for the UI origin is
  **not strict**.
- **Production recommendation:** Adopt nonce/hash-based CSP where the framework
  allows; add DOMPurify for any user-derived HTML; security-review the UI.

### 6.10 Log injection

- **Threat:** Forged log lines or terminal escape sequences via user input.
- **Attack scenario:** A crafted `X-Request-ID` containing newlines/ANSI escapes.
- **Existing mitigation:** JSON structured logging (one object per line).
- **Phase 8 mitigation:** `sanitize_request_id` accepts only `[A-Za-z0-9_-]`
  within a length bound and regenerates a random ID otherwise; residual control
  characters rejected; logs carry only safe metadata (IDs, counts, sizes, codes).
- **Residual risk:** Any future field logged from raw input would reintroduce risk;
  guarded by policy and log-content tests.
- **Production recommendation:** Ship logs to a store that treats fields as data;
  add automated log-content scanning in CI.

### 6.11 Unsafe exception disclosure

- **Threat:** Stack traces or internal detail leak to clients.
- **Attack scenario:** Triggering an unhandled error to read paths, library
  versions, or PII in a traceback.
- **Existing mitigation:** Central `AppError` with safe codes/messages.
- **Phase 8 mitigation:** Global handlers return generic bodies —
  `unhandled_error_handler` → `INTERNAL_ERROR`; validation handler maps errors to
  stable codes **without echoing values or bodies**; `DEBUG` must be off in
  production (config validator).
- **Residual risk:** Server-side logs still record exception *types* (not values);
  a misconfiguration enabling `DEBUG` would leak more.
- **Production recommendation:** Enforce `DEBUG=false` via deployment policy; route
  detailed errors only to internal observability.

### 6.11a Cross-job artifact access

- **Threat:** Downloading an artifact belonging to a different job.
- **Attack scenario:** Requesting `/jobs/A/artifacts/{B_artifact}`.
- **Existing mitigation:** Artifacts are looked up scoped to their `job_id`.
- **Phase 8 mitigation:** `get_artifact(db, job_id, artifact_id)` requires both to
  match; mismatches return `ARTIFACT_NOT_FOUND`; downloads use `no-store` + `nosniff`.
- **Residual risk:** Without auth, a client that knows **both** UUIDs of a job it
  does not own can still access them (see §6.12).
- **Production recommendation:** Enforce ownership via authenticated sessions and
  per-object authorization.

### 6.12 IDOR without authentication

- **Threat:** Insecure direct object reference — acting on another user's job.
- **Attack scenario:** Enumerating or reusing a job UUID to read/delete/redact.
- **Existing mitigation:** Job identifiers are version-4 UUIDs (high entropy).
- **Phase 8 mitigation:** Strict UUID parsing (`INVALID_UUID`); expired jobs return
  `JOB_EXPIRED` (410); missing jobs return `JOB_NOT_FOUND` (404).
- **Residual risk:** **Opaque UUIDs are NOT a substitute for authorization.** There
  is no auth in Phase 8; anyone who obtains a UUID can act on that job.
- **Production recommendation:** Add authentication and per-user authorization on
  every job-scoped route before any shared/hosted deployment.

### 6.13 Browser caching of sensitive responses

- **Threat:** Sensitive downloads or summaries persist in browser/proxy caches.
- **Attack scenario:** A redacted document or result JSON recovered from disk cache
  on a shared machine.
- **Existing mitigation:** Artifact/audit responses set `Cache-Control: no-store, private`.
- **Phase 8 mitigation:** `SecurityHeadersMiddleware` applies `no-store, private`
  (+ `Pragma: no-cache`) to all `/api/v1/*` responses; downloads add `nosniff`.
- **Residual risk:** The browser may still hold objects in memory; OS-level swap or
  user "save as" is outside our control.
- **Production recommendation:** Serve over HTTPS, document shared-machine risk, and
  consider ephemeral, single-use download tokens.

### 6.14 Dependency compromise

- **Threat:** A malicious or vulnerable dependency (spaCy, Presidio, PyMuPDF,
  Pillow, OpenCV, Next.js, etc.).
- **Attack scenario:** A backdoored transitive package executes in the API or build.
- **Existing mitigation:** Pinned dependencies; minimal runtime image.
- **Phase 8 mitigation:** Dependency auditing wired into CI (`pip-audit` for the
  API, `npm audit` for the web) as part of the quality gates.
- **Residual risk:** Audits catch **known** advisories only; a novel supply-chain
  compromise or unpatched transitive dep can still ship.
- **Production recommendation:** SBOM generation, signed/pinned lockfiles, Dependabot/renovate,
  and periodic manual review of high-risk parsers.

### 6.15 Container escape assumptions

- **Threat:** Breaking out of the container to the host.
- **Attack scenario:** Exploiting a parser bug plus a kernel/runtime flaw to escape.
- **Existing mitigation:** Containers run as **non-root uid 10001**.
- **Phase 8 mitigation:** `no-new-privileges:true`, `cap_drop: ALL`,
  `read_only: true` root filesystem with a `tmpfs` `/tmp`, app code mounted
  read-only, and PostgreSQL not published to the host.
- **Residual risk:** Container isolation is **not** a security boundary against a
  kernel 0-day; the Docker socket/host remain trusted. No seccomp/AppArmor profile
  is applied in the MVP.
- **Production recommendation:** Add seccomp/AppArmor profiles, user namespaces, and
  a sandboxed runtime (gVisor/Kata) for parser workloads.

### 6.16 Temporary-file recovery

- **Threat:** Recovering deleted source/OCR files from disk.
- **Attack scenario:** Forensic recovery of unlinked files from the volume.
- **Existing mitigation:** Random names; restrictive POSIX permissions where
  supported; deletion on delete-now/expiry/reconcile.
- **Phase 8 mitigation:** OCR intermediates confined to `ocr-work/` under the upload
  root and unlinked after use; orphan reconciliation removes stray managed files and
  quarantine leftovers.
- **Residual risk:** Deletion is `unlink`, **not** secure erase; data may remain
  recoverable from the underlying storage until overwritten.
- **Production recommendation:** Use encrypted-at-rest, ephemeral storage; consider
  memory-backed or secure-wipe volumes; short TTLs.

### 6.17 Deletion / expiration races

- **Threat:** Concurrent analyze/redact/delete on the same job corrupting state or
  leaking a partially processed file.
- **Attack scenario:** A `DELETE` firing mid-redaction.
- **Existing mitigation:** DB `ON DELETE CASCADE` for entities/artifacts.
- **Phase 8 mitigation:** `JobLockRegistry` provides per-job exclusive locks for
  analyze/redact/delete (`JOB_BUSY` on contention); atomic `os.replace` for artifact
  writes; failure paths clean up quarantine/partial output.
- **Residual risk:** Locks are **in-process only** — safe for one API instance, not
  across replicas. TTL cleanup and a delete can still interleave benignly.
- **Production recommendation:** Distributed locks (e.g., Postgres advisory locks /
  Redis) and a coordinated cleanup worker for multi-instance deployments.

### 6.18 Database leakage of PII

- **Threat:** The database itself becomes a source of PII.
- **Attack scenario:** A DB dump reveals document text, values, or mappings.
- **Existing mitigation:** Schema stores metadata only.
- **Phase 8 mitigation:** `DetectedEntity` explicitly **never stores the detected
  substring/value**; `ProcessingJob` stores type/size/counts/coverage; no OCR or
  extracted text column exists. **No migration 005 / `AuditEvent` table was required
  — the schema was already minimized.** Result/audit payloads pass
  `assert_result_payload_is_safe`, which rejects banned keys
  (`storage_key`, `*_filename`, `path`, `ocr_text`, `extracted_text`, `full_text`,
  `pseudonym_mapping`, `detected_value`).
- **Residual risk:** Metadata (offsets, rectangles, category counts) can still leak
  *structural* information about a document; DB credentials default to a placeholder.
- **Production recommendation:** Encrypt at rest, rotate real secrets via a secret
  manager, restrict DB network access, and add row-level access controls with auth.

### 6.19 Generated-output verification failure

- **Threat:** A "redacted" artifact that still contains the sensitive content.
- **Attack scenario:** Redaction annotations applied but extractable text or pixels
  remain.
- **Existing mitigation (Phase 5/6):** Text pages use PyMuPDF true redaction;
  scanned/OCR/mixed pages use **rasterize → paint → rebuild** so original content
  streams and hidden text layers are not retained.
- **Phase 8 mitigation:** `verify_redaction` re-extracts output text and asserts
  forbidden values absent / required control text present; `verify_scanned_page_redaction`
  additionally checks no removable annotations remain, samples the fill color, and
  **re-OCRs** the page to confirm forbidden values are gone. Any failure →
  `REDACTION_VERIFICATION_FAILED` and no artifact is published. Substrings are never
  logged.
- **Residual risk:** Verification depends on re-extraction/re-OCR fidelity; unusual
  encodings, ligatures, or OCR misreads can cause both false failures and, in
  principle, missed residue. **Automated redaction is not a guarantee — users must
  review outputs.** Manual rectangles redact geometry only.
- **Production recommendation:** Add layout-aware and human-in-the-loop QA for
  high-stakes documents; expand verification corpora.

### 6.20 Denial-of-service limitations (acknowledged)

- **Threat:** Availability degradation.
- **Attack scenario:** Sustained in-limit request pressure on a single instance.
- **Existing / Phase 8 mitigation:** Size/length/page/pixel caps, per-process
  concurrency semaphores, per-job locks, and regex timeouts (see §6.5).
- **Residual risk:** **No distributed rate limiting, no IP throttling, no global
  quota, single instance.** A local actor can still cause slowdowns within limits.
- **Production recommendation:** API-gateway rate limiting, horizontal scaling, and
  queue-based processing.

---

## 7. Implemented security controls

### 7.1 Validation layers (defense in depth)

1. Streaming size enforcement during upload (before full buffering).
2. Signature sniffing + extension + declared MIME must agree.
3. Executable/archive rejection.
4. Structural validation (PyMuPDF for PDF, Pillow for images).
5. Active-content rejection for PDFs.
6. Pydantic request-schema validation with `extra=forbid` semantics and stable
   error codes.

### 7.2 Safe logging

Structured JSON logs record only request ID, job ID, validated type, byte size,
page/pixel counts, DPI, durations, counts, confidence averages, and safe error
codes. Never original/anonymized text, detected values, OCR text/TSV, filenames,
storage keys, or absolute paths. Log-content tests enforce this.

### 7.3 Path containment

Server-generated keys only; strict key regex; rejection of separators, `..`, null
bytes, and absolute/UNC/drive forms; `relative_to(base)` re-checks on every resolve.

### 7.4 Temporary storage

Random `.quarantine-<hex>` streaming target with `O_CREAT|O_EXCL` (+`O_NOFOLLOW`);
restrictive permissions on POSIX; atomic promotion via `os.replace`; upload volume
not mounted into the web container and not served as static content.

### 7.5 Deletion

`DELETE /api/v1/jobs/{job_id}` removes source, artifacts, OCR work, and DB rows
under a per-job lock; only symlinks-as-themselves or regular files are unlinked.

### 7.6 Expiration

`UPLOAD_TTL_MINUTES` (60) TTL; in-process `cleanup_loop`
(`UPLOAD_CLEANUP_INTERVAL_SECONDS`, 300); startup reconciliation removes expired
jobs and orphaned managed files.

### 7.7 Output verification

Re-extraction (text pages) and re-OCR + fill-sampling + annotation checks (scanned
pages) before an artifact is published; failures block publication.

### 7.8 OCR isolation

Tesseract via argv (no shell), hard timeout that kills the process, English only,
bounded DPI, random work files under `ocr-work/`, content never logged, concurrency
capped.

### 7.9 Active PDF content handling & metadata stripping

Inputs with embedded files/JS/unsafe actions are rejected. Generated PDFs are
sanitized (`sanitize_pdf_document`): metadata cleared, XML metadata deleted,
embedded files removed, and file-attachment/rich-media/link/popup annotations
stripped. Output images strip EXIF via canonical re-encode.

### 7.10 HTTP security headers

Applied by `SecurityHeadersMiddleware`: `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
`Cross-Origin-Resource-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`,
a restrictive `Permissions-Policy`, and a **strict CSP on the API origin**
(`default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`).
`Cache-Control: no-store, private` on `/api/v1/*`. HSTS is emitted **only** when
`ENABLE_HSTS=true` **and** `ENVIRONMENT=production`.

> **CSP caveat:** the Next.js web origin still requires `'unsafe-inline'` and
> `blob:` for the framework runtime and PDF.js rendering. **Do not claim the app's
> CSP is strict.** Only the API origin uses a locked-down CSP.

### 7.11 CORS

Explicit origin allow-list (`CORS_ORIGINS`, default `http://localhost:3000`);
**wildcards are rejected at config load**; credentials disabled; methods and headers
constrained; `Retry-After` and `X-Request-ID` exposed.

### 7.12 Trusted hosts

`TrustedHostMiddleware` with an explicit `ALLOWED_HOSTS` list (wildcards rejected);
bad `Host` headers → `INVALID_HOST` (400).

### 7.13 Concurrency limits

Per-process bounded semaphores for uploads, document jobs, OCR, and redactions
(`RESOURCE_BUSY` 429 with `Retry-After`); per-job locks (`JOB_BUSY` 409). Entity,
rectangle, recognizer, pattern-length, and audit-warning caps bound work per job.

### 7.14 Container security

Non-root uid 10001, `no-new-privileges`, `cap_drop: ALL`, read-only root FS with
`tmpfs /tmp`, read-only code mounts, Postgres unpublished, host ports bound to
`127.0.0.1`. The API image is large (**~2.1 GB**) because it bundles spaCy,
Tesseract, and OpenCV — a known size/footprint trade-off, not lightweight.

### 7.15 Dependency auditing

`pip-audit` (API) and `npm audit` (web) run in CI alongside lint/type/test/build.

---

## 8. Configurable limits (MVP defaults)

All are environment-configurable and validated at startup. Defaults are deliberately
conservative.

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_ENTITIES_PER_JOB` | 500 | Cap detections/regex matches per job |
| `MAX_RECTANGLES_PER_ENTITY` | 32 | Cap geometry per entity |
| `MAX_MANUAL_RECTANGLES` | 100 | Cap user-drawn redaction regions |
| `MAX_CUSTOM_RECOGNIZERS` | 10 | Cap user-supplied recognizers |
| `MAX_REGEX_PATTERN_LENGTH` | 200 | Bound custom pattern length |
| `MAX_AUDIT_WARNINGS` | 50 | Bound audit warning list |
| `MAX_CONCURRENT_OCR_JOBS` | 2 | Per-process OCR concurrency |
| `MAX_CONCURRENT_DOCUMENT_JOBS` | 4 | Per-process document-job concurrency |
| `MAX_CONCURRENT_UPLOADS` | 4 | Per-process upload concurrency |
| `MAX_CONCURRENT_REDACTIONS` | 2 | Per-process redaction concurrency |
| `CUSTOM_REGEX_TIMEOUT_SECONDS` | 0.25 | Hard timeout per custom-regex evaluation |

Related caps: `MAX_UPLOAD_BYTES` (20 MiB), `MAX_PDF_PAGES` (50),
`MAX_IMAGE_PIXELS` (40M), `MAX_TEXT_LENGTH` (50k), `OCR_MAX_PAGES` (20),
`OCR_TIMEOUT_SECONDS` (60), `UPLOAD_TTL_MINUTES` (60).

---

## 9. Custom recognizer / ReDoS safety

Custom regex recognizers are optional and fully sandboxed: count-limited,
length-bounded, name-validated, overly-broad patterns rejected
(`^(.*)+$`-style), a nested-quantifier heuristic rejects likely catastrophic
patterns, only `IGNORECASE`/`MULTILINE`/`ASCII` flags are allowed, patterns are
compiled before use, and every evaluation runs in a worker with a hard
`CUSTOM_REGEX_TIMEOUT_SECONDS` timeout (`REGEX_TIMEOUT` on expiry).

---

## 10. Residual risks (summary)

- No authentication/authorization; UUIDs are not access control.
- No TLS in the MVP; HSTS only in production mode.
- No distributed rate limiting; single-instance, in-process locks and cleanup.
- No malware scanning or parser sandboxing; validation ≠ disarming.
- `unlink` is not secure erase; temp data may be forensically recoverable.
- Container hardening is not a boundary against kernel/runtime 0-days.
- Automated redaction/verification can still err — human review required.
- Windows symlink/permission coverage is partial (tests may skip).

---

## 11. Security test coverage

Automated coverage spans unit and integration tests (backend `pytest`), frontend
(`vitest`), and Playwright end-to-end flows, plus lint/type/audit gates. The four
required E2E flows are: pasted-text → result, PDF upload → redacted PDF, invalid
upload → clear error, and delete job → inaccessible. See the completion report for
the live pass/skip counts of the current run; this document does **not** assert
specific passing counts, and some Windows symlink tests may be skipped.

---

## 12. Security Test Matrix

| Threat | Test | Expected mitigation | Automated / manual | Result | Remaining risk |
|--------|------|---------------------|--------------------|--------|----------------|
| Disguised executable upload | PE/ELF bytes as `.pdf` | `EXECUTABLE_CONTENT_REJECTED` | Automated | See completion report | Not malware scanning |
| Archive upload | ZIP/RAR/7z/GZIP | `ARCHIVE_CONTENT_REJECTED` | Automated | See completion report | Polyglots |
| MIME/signature mismatch | PNG bytes as PDF hint | `FILE_SIGNATURE_MISMATCH` | Automated | See completion report | Polyglots |
| Password-protected PDF | Encrypted PDF | `PASSWORD_PROTECTED_PDF` | Automated | See completion report | — |
| Oversized upload | > `MAX_UPLOAD_BYTES` | `FILE_TOO_LARGE` (413) | Automated | See completion report | — |
| Page-count abuse | PDF > `MAX_PDF_PAGES` | `PDF_PAGE_LIMIT_EXCEEDED` | Automated | See completion report | — |
| Active PDF content | JS/embedded/launch/annot | `ACTIVE_PDF_CONTENT_REJECTED` / `EMBEDDED_FILE_REJECTED` / `UNSAFE_PDF_ACTION_REJECTED` | Automated | See completion report | PyMuPDF 0-day; obfuscation |
| Image decompression bomb | Tiny→huge pixels | `IMAGE_PIXEL_LIMIT_EXCEEDED` | Automated | See completion report | Decoder 0-day |
| Multi-frame image | Animated PNG/GIF-like | `UNSUPPORTED_IMAGE_FRAMES` | Automated | See completion report | — |
| Path traversal | `../` storage key | `STORAGE_FAILURE` (rejected) | Automated | See completion report | Logic regressions |
| Symlink attack | Symlinked storage path | `UNSAFE_STORAGE_PATH` | Automated | See completion report | Windows may skip |
| ReDoS | Catastrophic custom regex | `INVALID_RECOGNIZER` / `REGEX_TIMEOUT` | Automated | See completion report | Heuristic bypass |
| Log injection | `X-Request-ID` with CRLF/ANSI | Sanitized/regenerated ID | Automated | See completion report | Policy-dependent |
| Exception disclosure | Force unhandled error | `INTERNAL_ERROR`, no trace | Automated | See completion report | `DEBUG` misconfig |
| Validation echo | Malformed body | Stable code, no value echo | Automated | See completion report | — |
| Cross-job artifact | `/jobs/A/artifacts/B` | `ARTIFACT_NOT_FOUND` | Automated | See completion report | No auth (needs UUIDs) |
| IDOR / expiry | Unknown/expired job UUID | `JOB_NOT_FOUND` / `JOB_EXPIRED` | Automated | See completion report | No authorization |
| Invalid UUID | Non-UUID path param | `INVALID_UUID` | Automated | See completion report | — |
| Browser caching | Inspect download headers | `no-store, private` + `nosniff` | Automated | See completion report | Memory/swap |
| CORS wildcard | `CORS_ORIGINS=*` | Startup config error | Automated | See completion report | — |
| Trusted host | Bad `Host` header | `INVALID_HOST` (400) | Automated | See completion report | — |
| Concurrency limit | Exceed slot | `RESOURCE_BUSY` (429) | Automated | See completion report | Per-process only |
| Job race | Concurrent op on job | `JOB_BUSY` (409) | Automated | See completion report | Single-instance |
| PII in logs | Scan logs after run | Counts/metrics only | Automated + manual | See completion report | Future field leaks |
| DB PII leakage | Inspect schema/rows | Metadata only, no values | Automated | See completion report | Structural metadata |
| Text redaction residue | Re-extract output | `REDACTION_VERIFICATION_FAILED` on residue | Automated | See completion report | Encoding edge cases |
| Scanned redaction residue | Re-OCR + fill sample | `REDACTION_VERIFICATION_FAILED` on residue | Automated | See completion report | OCR fidelity |
| Delete-now lifecycle | Delete then fetch | 404, files removed | Automated (E2E) | See completion report | Not secure erase |
| Expiration cleanup | TTL + reconcile | Expired/orphan removed | Automated | See completion report | Single-instance |
| Dependency audit | `pip-audit` / `npm audit` | No known criticals unaddressed | Automated (CI) | See completion report | Novel supply chain |

> "See completion report" indicates the live pass/skip result belongs to the
> most recent verification run; this document intentionally records no fixed counts.

---

## 13. Trust-but-verify: what is explicitly NOT guaranteed

- We do **not** guarantee an uploaded file is malware-free.
- We do **not** guarantee an anonymized output is free of all sensitive content —
  automated detection has false negatives; **users must review outputs**.
- We do **not** provide isolation between different users' data.
- We do **not** provide availability guarantees under load.

---

## 14. Production requirements (NOT implemented in Phase 8)

A real deployment **must** add the following before handling genuine personal data.
None of these are implemented in the Phase 8 MVP:

- **Authentication** for all non-health endpoints.
- **Authorization** (per-user/per-tenant ownership on every job-scoped route).
- **TLS** everywhere, with HSTS enabled.
- **Distributed rate limiting** and per-client quotas at the edge.
- **Coordinated cleanup** and distributed locking across multiple instances.
- **Malware scanning and sandboxed parsing/OCR** (seccomp/gVisor/microVM/CDR).
- **Secret management** (no default/placeholder DB credentials; rotation).
- **Monitoring, alerting, and audit logging** in a secure store.
- **Privacy-designed backups** (encrypted, minimized, short-lived, recoverable
  deletion semantics).
- **Incident response** process and data-breach procedures.
- **Multi-tenant isolation** (network, storage, and database).

Until these exist, treat this platform as a **local, single-user demonstration**.

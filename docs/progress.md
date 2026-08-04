# Progress — Intelligent PII Anonymization Platform

Tracks phase status, key outcomes, and unresolved risks. See
[implementation-plan.md](implementation-plan.md) for full phase definitions and
acceptance criteria.

Legend: not started, in progress, complete, blocked.

---

## Phase status

| Phase | Title | Status | Notes |
|-------|-------|--------|-------|
| 0 | Repository assessment and architecture | complete | |
| 1 | Project foundation | complete | Live Docker verified |
| 2 | Text PII analysis | complete | |
| 3 | Text review and anonymization | complete | Stateless review + selection offset fix |
| 4 | Secure document ingestion | complete | Upload + lifecycle only; no extraction |
| 5 | Text-based PDF processing | complete | Extract, review, true redaction |
| 6 | OCR and image processing | complete | Permanence: rasterize-rebuild |
| 7 | Results and exports | complete | No AuditEvent table |
| 8 | Security hardening and testing | complete | Threat model + hardening; no migration 005 |
| 9 | Deployment and portfolio polish | complete | Final MVP gate |

---

## Git repository verification

| Check | Result |
|-------|--------|
| Git root | `C:/Projects/intelligent-pii-anonymizer` |
| Branch | `master` |
| Remotes | None |
| Secrets / `.env` tracked | No |
| Playwright reports tracked | Ignored via `.gitignore` |
| Final commit created in Phase 9 | No (not requested) |

---

## Phase 3 — Text review and anonymization

**Status:** complete (2026-08-03 / 2026-08-04).

### Architecture decision

**Stateless client-side review.** The browser holds original text and review state. The
backend `POST /api/v1/anonymize/text` validates spans, transforms accepted entities, and
discards all sensitive data when the request ends. No PostgreSQL storage of pasted text,
detections, or pseudonym mappings.

### Work completed

- Review statuses: pending, accepted, rejected, edited, manually_added
- Two-panel text workspace: highlight preview + entity controls
- Accept / reject / accept-visible / reject-visible / restore / edit / manual-add / delete
- Filters: category, confidence, search
- Default + per-entity anonymization methods
- Strategies: replacement, redaction, masking, request-scoped pseudonymization
- Right-to-left transformation; review overlap resolution; conflicting manual error
- Results: preview, copy, download `.txt`, return-to-review, clear
- Backend/frontend tests + selected Playwright flow
- Docs updated (`api.md`, `implementation-plan.md`, `architecture.md`, `progress.md`)

### Commands executed and results

| Command | Result |
|---------|--------|
| `git rev-parse --show-toplevel` | `C:/Projects/intelligent-pii-anonymizer` |
| `git remote -v` | No remotes |
| Backend `ruff format --check` / `ruff check` / `mypy app` | Pass |
| Backend `pytest tests/ -v` | Pass — 40 tests |
| Frontend `format:check` / `lint` / `typecheck` / `test` / `build` | Pass — 8 Vitest tests |
| Frontend `npm run test:e2e` | Pass — 1 Playwright test |
| `docker compose up --build -d` | Pass |
| Live health | `ok` + `connected` + `X-Request-ID` |
| Live anonymize | Pass — masked email, rejected phone unchanged, manual PERSON pseudonymized |
| Live log review | Pass — counts/lengths only; no raw PII |
| Frontend `:3000` | HTTP 200 |

### Live anonymize sample (fictional)

Input entities: accepted email (mask), rejected phone, manual PERSON (pseudonymize).

Result: `Casey Okafor at f*************@example.com phone 902-555-0182`
(`transformed_count=2`, `rejected_count=1`).

### Known limitations

- Pending detections are treated as transformable (documented in UI).
- Audit-report download and persistent jobs deferred.
- Text redaction uses block characters; not PDF coordinate redaction.

### Phase 3 correction — manual selection offsets (2026-08-03)

**Issue:** Manual entity creation used `indexOf(selected)`, so selecting the second or
third identical substring incorrectly mapped to the first occurrence.

**Fix:** `apps/web/lib/selectionOffsets.ts` maps DOM Selection boundaries to source
offsets by walking text nodes under the preview container. No string search. Handles
repeated substrings, selections inside `<mark>` nodes, multi-node ranges, Unicode,
collapsed/empty selections, and selections outside the container.

**Tests:** `apps/web/tests/selectionOffsets.test.tsx` — 7 tests including second and
third identical occurrences.

| Command | Result |
|---------|--------|
| `vitest run tests/selectionOffsets.test.tsx` | Pass — 7 tests |
| `npm run lint` / `typecheck` / `vitest run` | Pass — 15 Vitest tests |
| `npm run test:e2e` | Pass — 1 Playwright test |

Phase 3 is complete after this correction.

### Privacy safeguards

- No durable storage of text/mappings.
- Logs exclude original text, anonymized text, values, and mappings.
- Server derives substrings from validated spans only.

### Phase 4 confirmation (pre-Phase-4)

No Phase 5 functionality. Phase 4 work begins below after this correction.

---

## Phase 4 — Secure document ingestion

**Status:** complete (2026-08-03).

### Work completed

- `POST /api/v1/documents` — streaming multipart upload with validation pipeline
- `GET /api/v1/jobs/{job_id}` / `DELETE /api/v1/jobs/{job_id}` — safe metadata + delete-now
- `ProcessingJob` model + Alembic `002_processing_jobs`
- Extension / MIME / signature agreement; executable/archive rejection
- PyMuPDF PDF validation only (corruption, password, page count) — no text extraction
- Pillow image validation only (decode, format, pixels) — no OCR
- Randomized storage keys under `TEMP_UPLOAD_DIR`; path containment
- TTL cleanup + startup reconciliation (single-instance in-process task)
- Frontend upload mode with drag/drop, safe metadata, delete confirmation
- Backend/frontend/Playwright tests with fictional fixtures only

### Limits (defaults)

20 MiB upload, 50 PDF pages, 40M image pixels, 60-minute TTL, 5-minute cleanup.

### Explicitly out of scope (not implemented)

PDF text extraction, coordinate mapping, PDF redaction, OCR, Tesseract, OpenCV,
image redaction, artifact downloads, history pages, auth, Redis/Celery, cloud storage.

### Commands and results

| Command | Result |
|---------|--------|
| `git rev-parse --show-toplevel` | `C:/Projects/intelligent-pii-anonymizer` |
| `git remote -v` | No remotes |
| Backend `ruff format` / `ruff check` / `mypy app` | Pass |
| Backend `pytest tests/` | Pass — 113 tests |
| Frontend `format:check` / `lint` / `typecheck` / `test` / `build` | Pass — 25 Vitest |
| Frontend `npm run test:e2e` | Pass — 3 Playwright tests |
| `docker compose config` / `up --build -d` | Pass |
| `docker compose ps` | postgres/api healthy; web up; frontend HTTP 200 |
| `alembic downgrade -1` then `upgrade head` (API container) | Pass — `002_processing_jobs` |
| Live PDF/PNG/JPEG upload | 201 with safe metadata only |
| Live PE disguise / password PDF / oversize | 400 / 400 / 413 |
| Live DELETE then GET | 404 `JOB_NOT_FOUND` |
| Upload dir public routes | HTTP 404 (not exposed) |
| Pasted-text analyze (live) | Pass |

### Known limitations

- Signature checks are not malware scanning.
- In-process cleanup assumes one API instance.
- Windows host permission bits are not POSIX-equivalent.
- Phase 4 stores files only; no document analysis yet. *(superseded by Phase 5 for text PDFs)*

---

## Phase 5 — Text-based PDF processing

**Status:** complete (2026-08-03).

### Work completed

- PyMuPDF word-level extraction with global offsets (`PAGE_SEPARATOR = \\n\\f`)
- Offset→rectangle mapping without string search (repeated values supported)
- `DetectedEntity` / `GeneratedArtifact` models + Alembic `003_phase5_entities_artifacts`
- Analyze / entity review / manual rectangles / true redaction / verification / download
- Image-only PDFs return `OCR_REQUIRED` (no Tesseract/OpenCV)
- PDF.js preview with overlays, zoom, page navigation
- Backend **131** pytest tests; frontend **27** Vitest tests

### Explicitly out of scope

OCR, scanned-PDF processing, Tesseract, OpenCV, image redaction, PNG/JPEG anonymization.

### Commands (final)

| Command | Result |
|---------|--------|
| Backend ruff / mypy / pytest | Pass — 131 tests |
| Frontend format/lint/typecheck/test/build | Pass — 27 Vitest |
| `alembic` 003 upgrade/downgrade (dev DB) | Verified in Docker after rebuild |
| Docker rebuild | Pass |

---

## Phase 5 correction — Playwright PDF workflow gap (2026-08-03)

**Issue:** Phase 5 reported three Playwright tests (pasted text, upload/delete, invalid upload)
but lacked automated browser coverage for the text-PDF analysis/redaction workflow and the
image-only `OCR_REQUIRED` path.

**Fix:**

- Added `apps/web/e2e/pdf-phase5.spec.ts` with two focused flows using generated fictional
  fixtures under `samples/fictional/`
- Added `scripts/generate_phase5_e2e_fixtures.py` to regenerate those fixtures
- Hardened PDF draw-mode so detection overlays do not steal pointer events while drawing
- Switched manual rectangle drawing to pointer events with capture for reliable drag
- Sanitized Playwright config (list reporter; traces/screenshots/videos off) and expanded
  `.gitignore` for Playwright outputs

### New Playwright coverage

1. **Text-based fictional PDF** — upload → open review → analyze → confirm overlays →
   reject one entity → accept another → draw manual rectangle → generate redacted PDF →
   download artifact → confirm completion → confirm no storage key / upload path / internal
   fixture filename in the UI
2. **Image-only fictional PDF** — upload → analyze → `OCR_REQUIRED` → no full-analysis claim →
   no artifact generated

### Commands and results

| Command | Result |
|---------|--------|
| `npx playwright test e2e/pdf-phase5.spec.ts` | Pass — 2 tests |
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test` (Vitest) | Pass — 27 tests |
| `npm run build` | Pass |
| `npm run test:e2e` (full suite) | Pass — 5 tests |

Phase 5 Playwright gap is closed. Phase 6 begins below.

---

## Phase 6 — OCR and image processing

**Status:** complete (2026-08-03 / 2026-08-04).

### Work completed

- Tesseract OCR adapter (argv subprocess, timeout, injectable; English only)
- OCR work directory under upload root with random names + cleanup/reconciliation
- Conservative preprocessing (grayscale/threshold/optional mild deskew; max 2 OCR passes)
- OCR text index with stable offsets (no substring-search mapping)
- Separate detection vs OCR confidence + low-OCR flags
- PDF page render at configurable DPI + pixel↔PDF transforms (incl. rotation helpers)
- Document analysis routing: embedded-text pages, OCR for scanned/image pages, PNG/JPEG OCR
- Migration `004_phase6_ocr_metadata` (safe entity/job coverage fields only)
- Image irreversible redaction + OCR/pixel verification helpers
- Image review workspace + PDF UI OCR source/confidence labels
- Docker API image installs `tesseract-ocr` + `tesseract-ocr-eng` + `opencv-python-headless`
- CI installs Tesseract; `.env.example` / Compose OCR settings documented

### Explicitly out of scope (not implemented)

JSON audit reports, persistent history, auth/RBAC, payments, Redis/Celery/K8s, DOCX,
browser extensions, paid OCR/AI APIs, Phase 7+ results pages.

### Commands and results

| Command | Result |
|---------|--------|
| `git rev-parse --show-toplevel` | `C:/Projects/intelligent-pii-anonymizer` |
| `git remote -v` | No remotes |
| Backend `ruff format --check` / `ruff check` (ignore UP042 legacy enums) / `mypy app` | Pass |
| Backend `pytest tests/` | Pass — **136 passed, 1 skipped** |
| `alembic upgrade` to `004_phase6_ocr_metadata` | Pass (API container startup) |
| Frontend typecheck / lint / vitest / build | Pass — **27 Vitest** |
| Playwright `e2e/pdf-phase5.spec.ts` | Pass — 2 tests (text PDF workflow + image-only OCR path) |
| `docker compose up --build` | Pass — postgres/api healthy; web HTTP 200 |
| Live PNG OCR analyze (fictional email/phone) | Pass — `source_kind=ocr`, confidences present, no path leak |
| Live scanned blank PDF OCR | Pass — OCR page path runs; 0 detections on blank fixture |
| Live log scan for fictional values / paths | Pass — counts/metrics only |
| API image size | **2.1GB** (not lightweight; includes spaCy + Tesseract + OpenCV) |

### Known limitations / unresolved risks

- Scanned-page PDF redaction uses **Approach 2 (rasterize → paint → rebuild)** for OCR,
  scanned, and mixed image pages. Pure embedded-text pages retain Phase 5 PyMuPDF text
  redaction. Rebuilt pages are normalized to rotation 0 while preserving visual
  `page.rect` dimensions (file size / quality tradeoff: scanned pages become full-page
  rasters at the configured DPI).
- Synchronous OCR page limit (`OCR_MAX_PAGES=20`) and single-instance cleanup remain MVP
  constraints.
- OCR accuracy varies for handwriting, low resolution, and complex layouts — UI warns users
  to review manually.
- Default Pillow font OCR fixtures can be low-confidence; high-contrast large fonts reduce
  flakiness for real Tesseract tests.

### Privacy safeguards

- No OCR text / detected values persisted in PostgreSQL.
- OCR work files use random names under controlled upload subtree; deleted after use and on
  job delete/expire/startup reconcile.
- Logs record safe metrics (counts, DPI, durations, average confidence) — not OCR text,
  filenames, paths, or storage keys.

### Phase 6 closure corrections (2026-08-03 / 2026-08-04)

1. **Irreversible scanned-PDF redaction** — rasterize/paint/rebuild for pixel pages;
   PyMuPDF `apply_redactions` retained only for pure embedded-text pages.
2. **Permanence + rotation + mixed-PDF tests** added under
   `tests/processing/pdf/test_scanned_permanence.py` and
   `tests/services/test_mixed_pdf_api.py` (Tesseract required for mixed API tests).
3. **Skipped test resolution** — `test_docker_compose_defines_required_services` previously
   skipped when `docker-compose.yml` was absent inside the API container. Fixed by mounting
   `./docker-compose.yml:/app/docker-compose.yml:ro` and asserting the file is present
   (converted to a hard pass). Equivalent coverage: Compose contract markers for postgres/api/web,
   healthchecks, and OCR env keys.
4. OCR↔PDF transforms now use PyMuPDF `rotation_matrix * zoom` for 0/90/180/270 alignment.

| Command | Result |
|---------|--------|
| Host `pytest tests/ -q -rs` | **158 passed, 2 skipped** (mixed PDF needs host Tesseract) |
| Docker `pytest tests/ -q -rs` | **160 passed, 0 skipped** |
| Backend ruff / mypy | Pass |

---

## Phase 7 — Results and exports

**Status:** complete (2026-08-03 / 2026-08-04).

### AuditEvent decision

**No `AuditEvent` model or migration `005`.** Safe result and audit payloads are generated
from existing `ProcessingJob`, `DetectedEntity`, and `GeneratedArtifact` metadata
(`analysis_coverage_json`, review statuses, category/method counts, artifact metadata).

### Work completed

- `GET /api/v1/jobs/{job_id}/result` — safe summary
- `GET /api/v1/jobs/{job_id}/audit-report` — versioned JSON download
- Safe download headers (`nosniff`, `Cache-Control: no-store, private`) on artifacts/audit
- `DocumentResultPanel` for PDF/image jobs; text result audit download (client-side safe JSON)
- Delete-now / expiration already cover entities, artifacts, OCR work, and job rows
- Backend/frontend/Playwright coverage for results and audit

### Commands and results

| Command | Result |
|---------|--------|
| Backend ruff / mypy / pytest (Docker) | Pass — **160** tests |
| Frontend format/lint/typecheck/vitest/build | Pass — **29** Vitest |
| Playwright phase5 + phase7 + review-flow | Pass — **6** tests |
| `docker compose config` / `up --build -d` / `ps` | Pass — postgres/api healthy; web up |
| Live `scripts/live_phase7_check.py` | Pass — result/audit/delete → 404 |
| Migration | **None required** (no AuditEvent / no new columns) |

### Known limitations

- No persistent history page; pasted text remains request-scoped.
- Production authorization is still open (Phase 8).
- Single-instance cleanup remains an MVP constraint.

---

## Phase 8 — Security hardening and testing

**Status:** complete (2026-08-04).

### Scope

Security hardening, expanded automated testing, and completion of the security and
privacy documentation for a **local, single-instance, unauthenticated MVP**. This
phase does not add authentication, authorization, TLS, or distributed
infrastructure — those are explicitly deferred to production (see below).

### Work completed

- **Threat model + security docs** — `docs/security.md` rewritten with assets,
  trust boundaries, entry points, attacker capabilities, sensitive-data lifecycle,
  a structured threat model (Threat / Attack scenario / Existing mitigation /
  Phase 8 mitigation / Residual risk / Production recommendation), implemented
  controls, configurable limits, residual risks, production requirements, and a
  Security Test Matrix.
- **User-facing privacy doc** — `docs/privacy.md` rewritten (local processing, no
  paid AI/LLM, 60-min retention, delete-now, DB stores/does-not-store, OCR
  locality, logging/audit exclusions, browser/clipboard/UUID/recovery/backup
  limitations, detection limitations, required demonstration warning).
- **HTTP security headers** — `SecurityHeadersMiddleware` (nosniff, no-referrer,
  frame DENY, CORP/COOP same-origin, Permissions-Policy, strict CSP on the API
  origin, `no-store, private` on `/api/v1/*`, HSTS only in production).
- **CORS + trusted hosts** — explicit allow-lists with wildcard rejection at config
  load; bad `Host` → `INVALID_HOST`.
- **Request-ID sanitization / log-injection defense** — `[A-Za-z0-9_-]`,
  length-bounded, control-char rejection, random regeneration.
- **Safe exception handling** — generic `INTERNAL_ERROR`; validation errors mapped
  to stable codes without echoing request values; `DEBUG` blocked in production.
- **Concurrency + resource limits** — per-process bounded semaphores (uploads,
  document jobs, OCR, redactions) → `RESOURCE_BUSY` (429); per-job locks →
  `JOB_BUSY` (409); entity/rectangle/recognizer/pattern-length/audit caps.
- **ReDoS-safe custom recognizers** — length/broadness/nested-quantifier checks,
  allow-listed flags, hard `CUSTOM_REGEX_TIMEOUT_SECONDS` timeout.
- **File-lifecycle hardening review** — path containment, symlink/O_NOFOLLOW/O_EXCL
  handling, atomic promotion, active-PDF-content rejection, generated-PDF metadata
  stripping, EXIF-free image outputs, orphan/TTL reconciliation.
- **Output verification** — re-extraction (text) and re-OCR + fill-sampling +
  annotation checks (scanned) before publishing artifacts.
- **Dependency auditing** — `pip-audit` (API) and `npm audit` (web) wired into CI.
- **Container security** — non-root uid 10001, `no-new-privileges`, `cap_drop: ALL`,
  read-only root FS + `tmpfs /tmp`, Postgres not published, host ports on `127.0.0.1`.

### Commands and results

| Command | Result |
|---------|--------|
| Backend `ruff format` / `ruff check` / `mypy app` | Pass |
| Backend host `pytest tests/ -q -rs` | **188 passed, 3 skipped** |
| Backend Docker `pytest tests/security` | **31 passed** (symlink exercised on Linux) |
| Frontend format/lint/typecheck/vitest/build | Pass — **34 Vitest** |
| `npm audit --audit-level=critical` | Pass (high Next 15 findings accepted; see `docs/dependency-audit.md`) |
| `bandit -r app -ll` | Pass after documented `# nosec` for B108/B104 |
| `docker compose config` / `up --build -d` / `ps` | Pass — postgres/api healthy; web up |
| Live health / frontend | `ok` + `connected`; web HTTP 200 |
| Live security smoke (`scripts/live_phase8_check.py`) | Pass — headers, CORS, host reject, PE reject, cross-job, delete |
| Published ports | API/web `127.0.0.1` only; Postgres not published |
| Container users | API uvicorn **uid 10001**; web **uid 10001** |
| Image sizes | API **2.14 GB**; web **342 MB** |
| Migration | **None required** — no `AuditEvent`, no migration 005 |

### Known limitations / unresolved risks

- **No authentication or authorization.** Opaque UUIDs are **not** access control.
- **No TLS** in the MVP; HSTS is emitted only in production mode.
- **No distributed rate limiting**; concurrency limits and per-job locks are
  **per API process**; cleanup is single-instance (in-process + startup reconcile).
- **No malware scanning or parser sandboxing** — validation is not disarming.
- Deletion is `unlink`, **not** secure erase; temp data may be recoverable.
- CSP for the **Next.js web origin** still requires `'unsafe-inline'` and `blob:`
  (framework + PDF.js) — the app CSP is **not** strict; only the API origin is.
- **Windows symlink tests may be skipped** (no `O_NOFOLLOW` / POSIX modes).
- **API Docker image is ~2.1 GB** (spaCy + Tesseract + OpenCV) — not lightweight.
- PostgreSQL is **not published to the host**; host ports bind to `127.0.0.1`.
- Containers run **non-root (uid 10001)**.
- **No `AuditEvent` model and no migration 005** — audit JSON is generated from
  existing safe metadata; the schema was already minimized.

### Not implemented in Phase 8 (production requirements)

Authentication, authorization, TLS, distributed rate limiting, coordinated
multi-instance cleanup, malware scanning / sandboxing, secret management,
monitoring/alerting, privacy-designed backups, incident response, and multi-tenant
isolation. See
[security.md §14](security.md#14-production-requirements-not-implemented-in-phase-8).

### Phase 9 confirmation

**Phase 9 (deployment and portfolio polish) is complete.** See Phase 9 section below.

---

## Phase 9 — Deployment and portfolio polish

**Status:** complete (2026-08-04).

### Work completed

- Final UI polish: IBM Plex typography, teal accent identity, shared button/panel classes,
  updated copy for Phases 5–8 capabilities, aligned PDF/image entity types with backend
- Accessibility: focus rings, reduced-motion, axe smoke tests (`jest-axe`), docs notes
- Fictional samples + `scripts/generate_fictional_samples.py` (path-contained)
- Portfolio screenshots in `docs/images/` via explicit `npm run screenshots`
- Architecture Mermaid diagrams updated to match implementation (no AuditEvent/settings myths)
- README rewrite; `docs/portfolio.md`, `docs/demo-guide.md`, `docs/deployment.md`,
  `docs/testing.md`, `docs/accessibility.md`
- GitHub prep: `SECURITY.md`, `CONTRIBUTING.md`; license decision documented as pending
- Compose fix: `DAC_OVERRIDE` for upload-volume ownership repair under `cap_drop: ALL`
- Fixed truncated `.env.example` (`CUSTOM_REGEX_TIMEOUT_SECONDS`)
- Removed accidental tracked `apps/api/_t.pdf`

### Final quality gates (executed)

| Command | Result |
|---------|--------|
| Backend `ruff format --check` / `ruff check` / `mypy app` | Pass |
| Host `pytest tests/ -q -rs` | **188 passed, 3 skipped** |
| Docker `pytest tests/ -q -rs` | **191 passed, 0 skipped** |
| Frontend format/lint/typecheck | Pass |
| Vitest | **36 passed** (includes 2 axe smoke tests) |
| `npm run build` | Pass |
| `npm audit --audit-level=critical` | Pass (high Next findings accepted; see dependency-audit) |
| `bandit -r app -ll` | Pass (no medium/high) |
| Host `pip-audit` | Noisy (92 findings across global/conda env) — treat CI/clean env as source of truth |
| Docker `pip-audit` | Failed: read-only FS cannot create `/root/.cache` |
| Playwright `npm run test:e2e` | **10 passed** |
| Screenshots `npm run screenshots` | **10 passed** → `docs/images/*.png` |
| `docker compose config` / `up --build -d` / `ps` | Pass — postgres/api healthy; web up |
| Live health / frontend | `ok` + `connected`; HTTP 200 |
| Live text analyze/anonymize | Pass (fictional Casey Okafor) |
| Live PDF + PNG analyze + delete | Pass via curl |
| Live `scripts/live_phase8_check.py` | Pass |
| Security headers | `nosniff`, `DENY`, `no-referrer` present |
| Tesseract in API image | `eng` (+ `osd`) listed |
| API process user | **uid 10001** (uvicorn) |
| Image sizes | API **2.14 GB**; web **343 MB** |
| Git remotes | **None** |
| Final commit | **Not created** (awaiting explicit instruction) |

### Fictional samples

`fictional-text-example.txt`, `fictional-text-document.pdf`,
`fictional-scanned-document.pdf`, `fictional-mixed-document.pdf`,
`fictional-id-card.png`, `fictional-contact-sheet.jpg`, plus `samples/fictional/README.md`.

### Screenshots

`docs/images/01-home-input.png` … `10-delete-now-confirmation.png` (fictional data only).

### Unresolved limitations (unchanged production gaps)

No auth/TLS/distributed cleanup/malware scanning; UUID ≠ access control; API image ~2.1 GB;
axe smoke ≠ WCAG certification; host pip-audit polluted by global packages; license not yet
chosen.

### MVP completion

**Phases 0–9 are complete** for the local portfolio MVP. Do not start additional phases
unless explicitly instructed. Do not push or create a GitHub remote unless instructed.

---

## Next step

Create a dedicated GitHub repository and push when authorized. Recommended commit message:

```text
docs: complete Phase 9 portfolio polish and final MVP gates
```

Manual GitHub steps are listed in the Phase 9 completion report / README clone placeholder.

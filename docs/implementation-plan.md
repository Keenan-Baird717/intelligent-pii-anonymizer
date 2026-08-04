# Implementation Plan — Intelligent PII Anonymization Platform

This plan defines the phased delivery of the platform, with objectives, key files,
tasks, and acceptance criteria for each phase. It complements
[architecture.md](architecture.md) and is tracked in [progress.md](progress.md).

Target timeline: approximately two weeks for one AI-assisted developer.

Working agreement for every phase after Phase 0:

- Implement one phase at a time.
- At the end of each phase: run the relevant tests, run formatting and linting, run type
  checking, build the affected applications, summarize changed files, explain important
  design decisions, update [progress.md](progress.md), list unresolved risks, then stop
  and wait for explicit instruction to continue.
- Never claim a command, test, migration, or build works without actually running it and
  inspecting the result. Never hide failing tests or disable quality checks.

---

## Repository state (as of Phase 0)

- The project directory was an empty greenfield folder with no code, docs, Docker, or CI.
- The parent `C:\Projects` folder is a git repo tied to an unrelated remote.
- **Decision:** initialize a dedicated git repository inside the project root as the
  first step of Phase 1.

---

## Proposed repository structure

```text
intelligent-pii-anonymizer/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/v1/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   ├── recognizers/
│   │   │   ├── processing/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── alembic/
│   │   └── pyproject.toml
│   └── web/
│       ├── app/
│       ├── components/
│       ├── features/
│       ├── hooks/
│       ├── lib/
│       ├── types/
│       └── tests/
├── docs/
│   ├── implementation-plan.md
│   ├── architecture.md
│   ├── security.md
│   ├── privacy.md
│   ├── progress.md
│   └── api.md
├── samples/fictional/
├── scripts/
├── .github/workflows/
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

---

## Phase 0 — Repository assessment and architecture

**Status:** complete.

**Objectives:** inspect repository, define architecture, identify risks, create the
planning and documentation set, define quality commands. No product features.

**Deliverables:**
- `docs/implementation-plan.md` (this file)
- `docs/architecture.md`
- `docs/progress.md`
- `docs/security.md` (stub, completed in Phase 8)
- `docs/privacy.md` (stub, completed in Phase 8)

**Acceptance criteria:**
- All Phase 0 docs exist and are internally consistent.
- Architecture covers the detection pipeline, redaction strategy, and data retention.
- Risk register documented.
- Quality commands defined (not yet runnable — no code exists).

---

## Phase 1 — Project foundation

**Objectives:** scaffold the monorepo, configure PostgreSQL, Docker Compose, linting,
formatting, and type checking, add a health endpoint, environment configuration, safe
structured logging, and database migrations. Initialize a dedicated git repo.

**Key files:** `docker-compose.yml`, `apps/api/pyproject.toml`,
`apps/web/package.json`, `Makefile`, `.env.example`, `apps/api/app/main.py`,
`apps/api/alembic/`, `.github/workflows/`.

**Tasks:**
- Run `git init` in the project root; add `.gitignore` excluding uploads, `.env`, build
  output, and local databases.
- Scaffold FastAPI app with health route and structured logging.
- Scaffold Next.js app that loads and calls the health endpoint.
- Configure Ruff, mypy, Pytest, ESLint, Prettier, Vitest.
- Configure Docker Compose (web + api + postgres) with health checks.
- Establish Alembic and an initial migration.

**Acceptance criteria:**
- `docker compose up --build` starts web, api, and postgres.
- `GET /api/v1/health` returns 200.
- Frontend loads at its configured port.
- Alembic initial migration applies cleanly.
- Backend quality commands (ruff, mypy, pytest smoke) pass.
- Frontend quality commands (eslint, tsc, vitest smoke, build) pass.

---

## Phase 2 — Text PII analysis

**Status:** complete.

**Objectives:** implement `POST /api/v1/analyze/text`, integrate Presidio and spaCy, add
deterministic regex recognizers, Canadian postal-code/phone/SIN/credit-card validation,
entity normalization, overlap resolution, and confidence normalization.

**Key modules:** `apps/api/app/recognizers/`, `apps/api/app/processing/detection/`,
`apps/api/app/schemas/`.

**Acceptance criteria:**
- Fictional sample text produces expected detections with confidence and source.
- No paid AI service required.
- Unit tests: email, phone, Canadian postal code, SIN validation, Luhn, custom
  recognizers, normalization, overlap resolution cases.
- Integration test: analyze-text endpoint end-to-end.

---

## Phase 3 — Text review and anonymization

**Status:** complete.

**Objectives:** build the text-analysis review workspace, highlight entities, support
accept/reject/edit/add, implement replacement/masking/redaction/pseudonymization for
pasted text. Review state is **client-side / stateless** — do not permanently store
submitted text, detections, or pseudonym mappings in PostgreSQL.

**Key modules:** `apps/api/app/processing/anonymization/`,
`apps/api/app/services/anonymization.py`, `apps/web/features/review/`.

**Acceptance criteria:**
- Users can complete the entire pasted-text workflow (analyze → review → anonymize).
- Pseudonyms remain consistent within a request; distinct values do not collide.
- Rejected detections remain unchanged in output.
- Backend and frontend tests pass.
- No durable PII storage for the text workflow.

**Deferred from earlier plan draft:** persistent job entity APIs and audit-report download
(not required for Phase 3 MVP per privacy-preserving architecture).

---

## Phase 4 — Secure document ingestion

**Status:** complete.

**Objectives:** add multipart file uploads, validate MIME type and file signatures,
enforce size and page-count limits, store files temporarily, add deletion and
expiration, prevent unsafe paths, and return safe errors.

**Key modules:** `apps/api/app/services/ingestion/`, `apps/api/app/api/v1/documents.py`,
`apps/api/app/api/v1/jobs.py`.

**Acceptance criteria:**
- Supported files (PDF/PNG/JPG/JPEG) accepted; unsupported and malicious-looking files
  rejected.
- Password-protected PDFs rejected with an actionable message.
- Files stored with random internal names; path traversal blocked.
- Files removed after expiration or manual deletion.
- Sensitive content is not logged (verified by test).

---

## Phase 5 — Text-based PDF processing

**Objectives:** extract PDF text and coordinates with PyMuPDF, map detections to page
regions, preview PDF pages in the frontend, apply true PDF redactions, and generate
downloadable output.

**Key modules:** `apps/api/app/processing/pdf/`, `apps/api/app/services/pdf/`,
`apps/web/features/pdf/`.

**Acceptance criteria:**
- Sensitive text is absent from extraction of the redacted output.
- Unrelated text remains present.
- The original input remains unchanged.
- Rejected detections are not redacted.
- Integration tests pass.
- Image-only PDFs return `OCR_REQUIRED` until Phase 6.

---

## Phase 6 — OCR and image processing

**Objectives:** add Tesseract OCR for PNG/JPEG and a fallback for scanned PDFs, preserve
OCR bounding boxes, display confidence warnings, and apply image redaction.

**Key modules:** `apps/api/app/processing/ocr/`, `apps/api/app/processing/image/`.

**Acceptance criteria:**
- Fictional test images are processed with visible redaction regions.
- Scanned-PDF OCR fallback triggers when embedded text is sparse.
- Output dimensions remain valid.
- Low-confidence OCR is clearly communicated in the UI.

---

## Phase 7 — Results and exports

**Status:** complete.

**Objectives:** build the results page, add downloadable artifacts, add the JSON audit
report, optionally add a CSV entity report, add processing statistics, and add a
delete-now action.

**Key modules:** `apps/web/features/results/`, `apps/api/app/services/results.py`,
`apps/api/app/schemas/results.py`.

**Acceptance criteria:**
- Complete document workflow works from upload through download for text, PDF, and image.
- Audit output excludes unnecessary raw PII.
- Expired artifacts are unavailable.

**Decision:** No `AuditEvent` table; audit JSON is generated from existing safe metadata.
CSV entity export deferred.

---

## Phase 8 — Security hardening and testing

**Status:** complete.

**Objectives:** expand unit and integration tests, add frontend tests, add selected
Playwright flows, add rate limiting and secure headers, review CORS and logging, review
the file lifecycle, and conduct a dependency audit. Complete `security.md` and
`privacy.md`.

**Acceptance criteria:**
- Quality gates pass.
- Four end-to-end flows pass: pasted-text workflow, PDF workflow, invalid upload error,
  delete job becomes inaccessible.
- Security and privacy documentation is current.
- No obvious raw-PII leakage in logs or audit output.

---

## Phase 9 — Deployment and portfolio polish

**Objectives:** create production configuration, deploy where practical, add an
architecture diagram and screenshots, add fictional demo files, complete the README, and
write portfolio/resume descriptions.

**Acceptance criteria:**
- A reviewer can run the project from the README (with Windows/PowerShell notes).
- The demo workflow is clear with fictional samples.
- All quality checks pass.
- Known limitations are documented.

---

## Recommended two-week schedule

| Days | Phase | Focus |
|------|-------|-------|
| 1 | 0–1 | Docs, scaffold, Docker, health |
| 2–3 | 2 | Text detection pipeline |
| 4–5 | 3 | Text review UI and anonymization |
| 6 | 4 | Secure uploads |
| 7–8 | 5 | Text PDF and redaction |
| 9–10 | 6 | OCR and images |
| 11 | 7 | Results and exports |
| 12–13 | 8 | Security, tests, E2E |
| 14 | 9 | README and polish |

---

## Quality commands

These are defined now and wired up during Phase 1. They are not runnable until code
exists.

### Root (via `Makefile`)

```text
make dev            # docker compose up --build
make down           # docker compose down
make test           # backend + frontend tests
make lint           # backend + frontend lint
make typecheck      # mypy + tsc
make build          # frontend production build
make backend-test   # pytest
make frontend-test  # vitest
make e2e            # playwright (Phase 8)
```

### Backend (`apps/api/`)

```bash
ruff check .
ruff format --check .
mypy app
pytest tests/ -v --cov=app
```

### Frontend (`apps/web/`)

```bash
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
npm run test:e2e   # Phase 8
```

### Docker (project root)

```bash
docker compose up --build
docker compose exec api pytest tests/ -v
docker compose exec web npm run test
```

### Windows / PowerShell notes

- Prefer Docker Desktop with WSL2 for parity with Linux CI.
- If `make` is unavailable, run the equivalent commands directly, e.g.
  `docker compose run --rm api pytest`.
- Reference container paths with forward slashes; mount host paths only through Compose
  volumes.

---

## Risk register

| ID | Risk | Impact | Likelihood | Mitigation |
|----|------|--------|------------|------------|
| R1 | PDF redaction leaves extractable text under annotations | High | Medium | PyMuPDF true redaction plus post-redaction extraction tests; document layout limits |
| R2 | OCR accuracy on poor scans | Medium | High | Confidence thresholds, UI warnings, preprocess only when it improves confidence |
| R3 | Presidio/spaCy false positives overwhelm review | Medium | Medium | Confidence filtering, overlap resolution, per-type toggles, default threshold 0.7 |
| R4 | Docker image size / build time (spaCy, Tesseract, OpenCV) | Medium | High | Multi-stage Dockerfile, pinned model size, layer caching |
| R5 | Windows dev friction (Docker, Tesseract paths) | Medium | Medium | Document PowerShell commands; recommend WSL2; all dev via Compose |
| R6 | Synchronous OCR timeout on large scans | Medium | Medium | Page/size limits; clear timeout errors |
| R7 | Pseudonym collision or non-determinism | Low | Low | Job-scoped seeded mapping; consistency unit tests |
| R8 | PII leakage via logs or audit metadata | High | Low | Structured logging policy, log-content tests, review checklist |
| R9 | Scope creep (DOCX, LLM detection, batch jobs) | High | Medium | Explicit out-of-scope list; phase gates |
| R10 | Two-week timeline slip | Medium | High | Strict MVP ordering; defer CSV export, optional deploy, larger spaCy model |
| R11 | Parent vs standalone git confusion | Low | Low | Dedicated `git init` in Phase 1; `.gitignore` excludes uploads and `.env` |
| R12 | Coordinate mapping errors on multi-line entities | Medium | Medium | Word-level span aggregation, configurable padding, visual QA with fixtures |

---

## Out of scope for the initial version

Payments, subscriptions, multi-tenant organizations, team workspaces, role-based access
control, production-scale Kubernetes, mobile apps, browser extensions, DOCX processing,
LLM-based primary detection, reversible tokenization, large batch jobs, complicated
analytics, and multiple cloud providers. Redis, Celery, and object storage are not added
unless the synchronous architecture proves demonstrably inadequate.

---

## Definition of done (MVP)

The MVP is complete when a user can:

1. Paste text or upload a supported document.
2. See processing progress.
3. Review detected entities with categories and confidence scores.
4. Accept, reject, edit, or add detections.
5. Select anonymization methods.
6. Generate and download anonymized output and an audit report.
7. Delete all processing data immediately.
8. Run the project locally with Docker Compose.
9. Run automated tests successfully.
10. Follow the README without undocumented setup.
11. Understand privacy and detection limitations.

---

## Testing requirements by layer

### Backend unit tests (Phases 2–8)

Email, phone, Canadian postal code, SIN validation, Luhn credit card, custom recognizers,
entity normalization, overlap resolution, masking, replacement, pseudonym consistency,
filename sanitization, file-signature validation, temp-file cleanup, safe logging.

### Backend integration tests (Phases 3–8)

Text through anonymized output; text PDF through redacted PDF; image through redacted
image; OCR fallback for scanned PDF; entity review; rejected detections unchanged;
manual detections; audit report; job deletion; expired-job cleanup.

### Frontend tests (Phases 3–8)

Text submission, file upload, unsupported-file error, detection rendering, filtering,
accept/reject, method selection, results display, download controls, delete-now, loading
and error states.

### End-to-end tests (Phase 8, Playwright)

1. Pasted text → review → anonymized result
2. PDF upload → review → redacted PDF
3. Invalid upload → clear error
4. Delete job → job inaccessible

### Fictional fixtures policy

All tests, samples, screenshots, and README examples use obviously fictional records.
No real personal information in tests, demo documents, seed data, or git history.

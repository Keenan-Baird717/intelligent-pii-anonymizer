# Portfolio — Intelligent PII Anonymization Platform

Assets for resumes, portfolios, and interviews. All claims match the implemented local MVP.

---

## One-sentence description

A privacy-first local MVP that detects PII in text, PDFs, and images with hybrid NLP, human review, true PDF redaction, and immediate deletion — without paid AI APIs.

---

## Short project description (≈70 words)

Intelligent PII Anonymization Platform is a Dockerized FastAPI and Next.js demonstration that finds personally identifiable information in pasted text, PDFs, and PNG/JPEG images. A hybrid Presidio, spaCy, regex, and checksum pipeline surfaces explainable detections for human accept/reject/edit. Text supports masking and pseudonymization; PDFs and images require irreversible redaction with verification. Temporary storage, delete-now, and minimized metadata keep sensitive content out of durable records.

---

## Full project description (≈280 words)

Many anonymization tools either over-trust automated detection or store sensitive documents longer than necessary. This project demonstrates a safer local workflow: validate input, extract or OCR when needed, detect with an explainable hybrid pipeline, require human review, then produce anonymized output that can be verified and deleted immediately.

The backend is FastAPI on Python 3.12 with PostgreSQL storing only safe job and entity metadata — not raw detected values, OCR text, or pseudonym mappings. Pasted-text analysis and anonymization are request-scoped and never persisted. Document uploads use streaming validation (extension, MIME, signature, structure), randomized storage keys, path containment, TTL expiration, and delete-now.

Detection combines deterministic regex and checksums (including Canadian postal codes, phone formats, and SIN checksum validation) with Presidio and spaCy. Overlap resolution and confidence scores support review. For PDFs, PyMuPDF maps character offsets to page rectangles without substring search so repeated values redact correctly. Embedded-text pages use true redaction annotations; scanned and OCR pages use a rasterize–paint–rebuild path so hidden text layers cannot survive. Images receive irreversible filled redactions after local Tesseract OCR.

The Next.js frontend provides a two-panel review workspace, OCR confidence cues, result summaries, safe JSON audit downloads, and accessibility-conscious controls. The stack runs with Docker Compose, GitHub Actions CI, dependency auditing, and extensive automated tests. The project intentionally omits authentication, multi-tenant SaaS features, and LLM-primary detection so the portfolio focus stays on NLP, document security, and privacy engineering.

---

## Resume bullets

- Built a hybrid PII detection pipeline combining Presidio, spaCy NER, regex recognizers, and checksum validation (Luhn / Canadian SIN) with overlap resolution and confidence scoring.
- Implemented human-in-the-loop review for text, PDF, and image workflows with accept/reject/edit, manual entities, and method selection where supported.
- Delivered coordinate-aware PDF redaction via PyMuPDF offset-to-rectangle mapping, plus irreversible rasterize–paint–rebuild for scanned and OCR pages with post-redaction verification.
- Added local Tesseract OCR for scanned PDFs and PNG/JPEG with bounding-box mapping, separate detection vs OCR confidence, and EXIF-free image outputs.
- Designed privacy-preserving temporary storage: randomized keys, path containment, 60-minute TTL, delete-now, and PostgreSQL metadata that excludes raw PII values.
- Hardened a Docker Compose MVP with non-root containers, security headers, concurrency limits, ReDoS-safe custom regex, CI quality gates, pip-audit/npm audit, and Playwright end-to-end flows.

---

## Interview talking points

### Why the project was built

To demonstrate end-to-end privacy engineering: detection quality is never assumed perfect, humans stay in the loop, and sensitive data is not retained longer than necessary.

### Architectural decisions

Synchronous-first FastAPI services instead of Redis/Celery for a clear local MVP. Stateless pasted-text path. Document jobs store metadata without raw values. No LLM as primary detector to keep costs, privacy, and explainability under control.

### Hardest technical problem

Mapping detections to PDF coordinates for repeated identical substrings without `indexOf`-style errors, then ensuring scanned-page redaction cannot leave extractable text under annotations.

### PDF redaction permanence

Embedded text uses PyMuPDF true redaction. Scanned pages are rebuilt as rasters with painted regions so original image objects and hidden text cannot remain.

### OCR coordinate mapping

Tesseract boxes are transformed with `rotation_matrix * zoom` into PDF user space; low OCR confidence is surfaced separately from detector confidence.

### Security and privacy tradeoffs

Validation is not malware scanning. Delete uses unlink, not secure erase. Opaque UUIDs are not authentication. Single-instance in-process cleanup is an MVP limit.

### Synchronous-first architecture

Keeps the demo operable with Compose alone; OCR page budgets and concurrency semaphores bound resource use.

### Testing strategy

Unit, integration, property-based, permanence, security, Vitest, Playwright, axe smoke, live Docker checks, and dependency audits — with fictional fixtures only.

### Production limitations

Needs TLS, authZ, secret management, distributed rate limiting, coordinated cleanup, malware scanning/sandboxing, monitoring, and multi-tenant isolation before any shared deployment.

### What would be built next

Authentication and private networking first; then optional async workers only if OCR volume demands it; never LLM-primary detection without a clear privacy model.

---

## Technology list

Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, Presidio, spaCy, PyMuPDF, Tesseract, OpenCV, Pillow, Next.js, React, TypeScript, Tailwind CSS, TanStack Query, PDF.js, Docker Compose, GitHub Actions, Pytest, Hypothesis, Vitest, Playwright, axe-core, Ruff, mypy, ESLint, Prettier, pip-audit, Bandit, npm audit.

---

## Skills demonstrated

- AI engineering / NLP
- OCR
- Backend development
- Frontend development
- Document processing
- Application security
- Privacy engineering
- Testing
- Docker
- CI/CD

# Intelligent PII Anonymization Platform

Privacy-focused platform for detecting and anonymizing personally identifiable information
(PII) in pasted text, with secure temporary document uploads (PDF/PNG/JPEG).

> This project is a demonstration tool. Automated PII detection can produce false positives
> or miss sensitive information. Users must review all results before sharing anonymized
> documents.

## Current status (Phase 7)

- Pasted-text analysis, human review, and anonymization (Phases 2–3)
- Secure document upload with validation and temporary storage (Phase 4)
- Text-based PDF extraction, coordinate mapping, review overlays, and true redaction (Phase 5)
- Tesseract OCR for scanned/mixed PDFs and PNG/JPEG, with irreversible image redaction (Phase 6)
- Unified result summaries, safe artifact downloads, JSON audit reports, delete-now, and expiration (Phase 7)
- **Not yet:** auth, history, RBAC, rate limiting expansion, portfolio polish (Phases 8–9)

> OCR and automated PII detection may miss sensitive information (handwriting, low
> resolution, complex layouts). Users must manually review every result.

## Prerequisites

- Docker Desktop with WSL2 (recommended on Windows)
- Node.js 22+ (for local frontend development without Docker)
- Python 3.12+ (for local backend development without Docker)

## Quick start (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- API health: http://localhost:8000/api/v1/health
- API docs (development): http://localhost:8000/docs

Temporary uploads are stored in the Docker volume `api_uploads` mounted only into the
API container at `/var/pii-uploads` (not exposed via the web app).

## Phase 4 upload limits (defaults)

| Limit | Default |
|-------|---------|
| Max upload size | 20 MiB |
| Max PDF pages | 50 |
| Max image pixels | 40,000,000 |
| Upload TTL | 60 minutes |
| Cleanup interval | 5 minutes |

See `.env.example` for upload and OCR settings (`OCR_*`, `TEMP_UPLOAD_DIR`,
`OCR_TEMP_DIR`).

### Phase 6 OCR defaults

| Setting | Default |
|---------|---------|
| Language | `eng` (English data baked into the API image) |
| Timeout | 60 seconds |
| Render DPI | 200 |
| Max OCR pages | 20 (synchronous MVP limit) |
| OCR work dir | `/var/pii-uploads/ocr-work` (API-only) |

Tesseract is installed in the **API** Docker image only. The frontend image has no OCR
dependencies. The API image is approximately **2.1GB** after spaCy + Tesseract + OpenCV
and is not claimed to be lightweight.

## Quality commands

### Backend (`apps/api`)

```bash
ruff format --check .
ruff check .
mypy app
pytest tests/ -v
alembic upgrade head
```

### Frontend (`apps/web`)

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

## Windows / PowerShell

```powershell
docker compose up --build -d
docker compose exec api pytest tests/ -v
Set-Location apps/web; npm run test
```

## Documentation

- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [Progress](docs/progress.md)
- [API reference](docs/api.md)
- [Security](docs/security.md)
- [Privacy](docs/privacy.md)

## License

See repository license file if present; otherwise treat as a private portfolio project.

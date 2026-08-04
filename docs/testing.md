# Testing guide

All fixtures and demos use **fictional** data only.

## Backend (`apps/api`)

| Suite | What it covers |
|-------|----------------|
| Unit | Recognizers, checksums, overlap, masking, path safety |
| Integration | Analyze/anonymize/upload/PDF/OCR/results/delete APIs |
| OCR / Tesseract | Skips on hosts without Tesseract; full pass in API container |
| PDF permanence | Embedded + scanned redaction verification |
| Property-based | Hypothesis cases where present |
| Security | Headers, path containment, ReDoS guards, cross-job access |

```bash
cd apps/api
ruff format --check .
ruff check .
mypy app
pytest tests/ -v
pytest tests/ -q -rs
pip-audit --desc on
bandit -r app -ll
```

## Frontend (`apps/web`)

| Suite | What it covers |
|-------|----------------|
| Vitest | Review state, upload, PDF/image workflows, results, privacy copy |
| axe smoke | Selected home/workspace automated checks (not full WCAG) |
| Playwright | Pasted text, PDF, results, security smoke |
| Screenshots | Explicit `npm run screenshots` only — not CI |

```bash
cd apps/web
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm audit --audit-level=critical
npm run test:e2e
```

## Docker live checks

```bash
docker compose config
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/api/v1/health
# Frontend: http://127.0.0.1:3000
```

Optional scripts: `scripts/live_phase8_check.py`, `apps/api/scripts/live_phase7_check.py`.

Final counts after each full Phase gate run are recorded in [progress.md](progress.md).

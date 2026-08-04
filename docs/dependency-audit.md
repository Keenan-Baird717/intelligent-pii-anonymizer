# Dependency audit notes — Phase 8

This file records how Phase 8 dependency findings were classified.
Automated scanners were run; findings are **not** claimed eliminated.

## Backend (`pip-audit`, `bandit`)

Commands:

```bash
cd apps/api
pip install -e ".[dev]"
pip-audit --desc on
bandit -r app -ll -x tests
```

### Constrained / upgraded packages

| Package | Action | Notes |
|---------|--------|-------|
| `pillow` | Raised to `>=12.3.0,<13` | Addresses multiple 2026 Pillow CVEs |
| `python-multipart` | Raised to `>=0.0.31,<0.1` | Addresses multipart DoS / parser CVEs |
| `pymupdf` | Raised to `>=1.26.7,<1.27` | Addresses CLI path-write issue in 1.26.6 |
| `starlette` | Minimum `>=0.49.1` | Host/path reconstruction fixes; TrustedHost also applied |

### Accepted temporarily / not applicable

| Finding | Classification | Justification |
|---------|----------------|---------------|
| PyMuPDF CLI path traversal (`_main_.py`) | Not applicable | Application imports the library API only; CLI entrypoint is not invoked |
| `python-multipart` `UPLOAD_DIR` path traversal | Not applicable | That optional multipart feature is unused; uploads use custom streaming + containment |
| Bandit B108 `/tmp` defaults | Accepted (documented) | Defaults are local-dev only; Docker Compose sets `/var/pii-uploads`; `# nosec B108` annotated |
| Host-environment pip-audit noise | Environmental | Host conda/global site-packages inflate counts; CI uses a clean runner |

## Frontend (`npm audit --audit-level=critical`)

High findings remain under Next.js 15.x / Vitest 2.x tooling:

| Area | Severity | Classification | Justification |
|------|----------|----------------|---------------|
| Vitest/Vite/esbuild (dev) | moderate/high | Accepted temporarily | Dev tooling only; Vitest bumped to 3.2.6 to clear critical UI-server advisory |
| `next` → `postcss` / `sharp` | high | Accepted temporarily | Fix path requires Next 16 major upgrade (`npm audit fix --force`); deferred to avoid Phase 8 scope creep |
| Production runtime | — | Partial | Standalone Next runtime still pulls Next's transitive sharp/postcss |

CI gate: **critical** severity fails the build. High findings are tracked here and in `docs/security.md`.

## Container scanning

Trivy / Docker Scout: **unverified** in this environment unless installed. Do not treat as passed.

## Policy

- Lockfiles / pinned ranges preserved.
- No blind major-version auto-fixes.
- No finding suppressed without classification above.

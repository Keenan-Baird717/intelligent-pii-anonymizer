# Contributing (local development)

This is primarily a portfolio MVP. External contributions are welcome for clear bug fixes
and documentation corrections, but large feature expansions are out of scope.

## Before you start

1. Use fictional data only — never commit real PII, uploads, or `.env` files.
2. Read [docs/architecture.md](docs/architecture.md) and [docs/privacy.md](docs/privacy.md).
3. Keep the project a focused local demo: no auth/SaaS scope creep unless explicitly agreed.

## License

A LICENSE file has **not** been selected yet. Do not assume open-source redistribution
rights until the owner adds an explicit license.

## Local workflow

```bash
cp .env.example .env
docker compose up --build
```

Backend quality (`apps/api`):

```bash
ruff format --check .
ruff check .
mypy app
pytest tests/ -v
```

Frontend quality (`apps/web`):

```bash
npm ci
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

Regenerate fictional samples:

```bash
python scripts/generate_fictional_samples.py
```

## Pull requests

- Keep diffs focused.
- Update docs when behavior changes.
- Add or adjust tests for fixes.
- Do not commit Playwright failure artifacts, uploads, or secrets.

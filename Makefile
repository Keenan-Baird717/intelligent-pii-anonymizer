.PHONY: dev down test lint typecheck build backend-test frontend-test backend-lint backend-format backend-typecheck frontend-lint frontend-format frontend-typecheck frontend-build migrate

dev:
	docker compose up --build

down:
	docker compose down

test: backend-test frontend-test

lint: backend-lint frontend-lint

typecheck: backend-typecheck frontend-typecheck

build: frontend-build

backend-test:
	cd apps/api && pytest tests/ -v

backend-lint:
	cd apps/api && ruff check .

backend-format:
	cd apps/api && ruff format --check .

backend-typecheck:
	cd apps/api && mypy app

frontend-test:
	cd apps/web && npm run test

frontend-lint:
	cd apps/web && npm run lint

frontend-format:
	cd apps/web && npm run format:check

frontend-typecheck:
	cd apps/web && npm run typecheck

frontend-build:
	cd apps/web && npm run build

migrate:
	cd apps/api && alembic upgrade head

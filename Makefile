.PHONY: up down logs verify migrate migrate-down migrate-rollback migrate-status \
        test-db-up test-db-down openapi gen-api-types check-api-types \
        backend-lint backend-test frontend-lint frontend-test lint test ci

UV ?= uv
PNPM ?= pnpm

# Load .env so DATABASE_URL / TEST_DATABASE_URL are available to recipes
# (docker compose reads it on its own).
ifneq (,$(wildcard .env))
include .env
export
endif

# yoyo migration CLI, scoped to the backend (reads backend/yoyo.ini).
YOYO = cd backend && $(UV) run yoyo

# Bring up the infrastructure services (Postgres, Neo4j, Phoenix; more as
# the stack grows). Waits until each reports healthy.
up:
	./scripts/up

down:
	docker compose down

logs:
	docker compose logs -f

# One-command end-to-end check: up + assert /health and the frontend.
verify:
	./scripts/verify

# --- Migrations (yoyo CLI, explicit up/down) ---
migrate:
	$(YOYO) apply --database "$(DATABASE_URL)"

# Roll back every applied migration. For a single targeted revision:
#   make migrate-rollback REVISION=0001.initial-schema
migrate-down:
	$(YOYO) rollback --all --database "$(DATABASE_URL)"

migrate-rollback:
	$(YOYO) rollback --revision "$(REVISION)" --database "$(DATABASE_URL)"

migrate-status:
	$(YOYO) list --database "$(DATABASE_URL)"

# --- Test infrastructure (isolated from the app databases) ---
test-db-up:
	docker compose --profile test up -d --wait postgres neo4j-test
	$(YOYO) apply --database "$(TEST_DATABASE_URL)"

test-db-down:
	docker compose --profile test down

# --- API contract: FastAPI schema -> frontend TypeScript types ---
# openapi.json (repo root) is the committed contract; api-schema.ts is
# generated from it. Regenerate and commit both whenever a model changes;
# CI fails if either is stale.
openapi:
	cd backend && PYTHONPATH=. $(UV) run python scripts/dump_openapi.py

gen-api-types: openapi
	cd frontend && $(PNPM) gen:api

# CI guard: regenerate the contract + types and fail if either is stale.
check-api-types: gen-api-types
	git diff --exit-code openapi.json frontend/src/lib/api-schema.ts

# --- Backend ---
backend-lint:
	cd backend && $(UV) run ruff check .
	cd backend && $(UV) run ruff format --check .
	cd backend && $(UV) run mypy
	cd backend && $(UV) run radon cc app --min C --total-average

backend-test:
	cd backend && $(UV) run pytest

# --- Frontend ---
frontend-lint:
	cd frontend && $(PNPM) lint
	cd frontend && $(PNPM) typecheck

frontend-test:
	cd frontend && $(PNPM) test

# --- Aggregate ---
lint: backend-lint frontend-lint

test: backend-test frontend-test

# What CI runs: contract freshness, lint, tests, and image builds.
ci: check-api-types lint test
	docker compose build

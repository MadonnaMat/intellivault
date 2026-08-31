.PHONY: up down logs migrate migrate-down migrate-rollback migrate-status \
        test-db-up test-db-down openapi gen-api-types \
        backend-lint backend-test frontend-lint frontend-test

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
	docker compose up -d --wait

down:
	docker compose down

logs:
	docker compose logs -f

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

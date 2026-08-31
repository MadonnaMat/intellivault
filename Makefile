.PHONY: up down logs backend-lint backend-test

UV ?= uv

# Bring up the infrastructure services (Postgres for now; more added as
# the stack grows). Waits until each reports healthy.
up:
	docker compose up -d --wait

down:
	docker compose down

logs:
	docker compose logs -f

# --- Backend ---
backend-lint:
	cd backend && $(UV) run ruff check .
	cd backend && $(UV) run ruff format --check .
	cd backend && $(UV) run mypy
	cd backend && $(UV) run radon cc app --min C --total-average

backend-test:
	cd backend && $(UV) run pytest

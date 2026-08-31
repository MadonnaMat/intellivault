# CLAUDE.md

Project-level instructions for Claude Code working in this repository.

## Workflow (required)

- **Start every task from a fresh `main`:** `git checkout main && git pull`, then
  `git checkout -b <descriptive-branch>`.
- **Never commit directly to `main`.** All work lands via a PR from a branch.
- **Commit at each logical stopping point** — not one giant commit at the end.
  Build features one coherent slice at a time (add the piece, verify it, commit).
  Do not write whole multi-service files (`docker-compose.yml`, `Makefile`, CI) up
  front — grow them one service/target at a time as that piece comes online.
- Every commit message ends with:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
- Before opening a PR: `make lint && make test` must pass, and if any
  request/response model changed, `make gen-api-types` and commit the result.

## Architecture notes

- **Ollama is not in docker-compose.** It runs on the host for GPU access;
  containers reach it via `host.docker.internal:11434`. `scripts/ollama-dev` is
  the only thing that starts/stops it or pulls models. This mirrors
  `~/go-rag-lab`.
- Compose overrides the `localhost` defaults from `.env.example` with in-network
  hostnames (`postgres`, `neo4j`, `phoenix`) for the `backend` container.
- **Config** lives in `backend/app/config.py` (pydantic-settings). Secrets
  (`NEO4J_PASSWORD`, `DATABASE_URL`) are required — no hardcoded defaults. The
  repo-root `.env` (gitignored) feeds native runs; compose injects env directly.
- **`/health`** (`app/health/`) probes Postgres, Neo4j, Phoenix and Ollama
  concurrently, each with a 3s timeout, failures captured not raised, and the
  whole batch bounded by an overall deadline so a stuck probe can't hang it. It
  aggregates to `ok` / `degraded` / `down` and returns HTTP 503 only when `down`.
  A failure of a **non-critical** dependency (`ServiceStatus.critical=False`,
  i.e. Phoenix) or a missing Ollama model is `degraded` — still 200.
  `/health/live` is the cheap liveness route for container healthchecks.
- **Observability** (`app/observability.py`) is best-effort: Phoenix being down
  never blocks start-up. `settings.tracing_enabled=false` disables it (tests).
- **Migrations** use the `yoyo` CLI (plain SQL + `.rollback.sql` in
  `backend/migrations/`). Nothing runs them automatically —
  `make migrate` / `docker compose run --rm migrate`.
- **Frontend API types** are generated from the FastAPI OpenAPI schema:
  `backend/scripts/dump_openapi.py` -> committed `openapi.json` ->
  `frontend/src/lib/api-schema.ts`. Never hand-edit either.
- **Tests use separate databases.** Postgres: `<db>_test` in the same instance
  (created by `docker/initdb`). Neo4j: a disposable `neo4j-test` service under the
  `test` compose profile. Never point tests at the app databases.
- Frontend components use **Ant Design**; all antd usage stays in client
  components (the RSC page is plain HTML). Interactive elements carry a
  `data-testid`; tests query by testid.

## Commands

| Command | Does |
|---------|------|
| `make up` / `make verify` | bring the stack up / + assert health |
| `make lint` / `make test` | both sides |
| `make backend-lint` | ruff check + format, mypy --strict, radon |
| `make backend-test` | pytest (coverage gate 85%) |
| `make frontend-lint` | eslint + tsc --noEmit |
| `make frontend-test` | vitest |
| `make migrate` / `migrate-down` / `migrate-status` | yoyo |
| `make gen-api-types` / `check-api-types` | regenerate / verify the API contract |
| `make openapi` | rewrite `openapi.json` from the FastAPI app |

## Ethos

Explicit steps, not magic. Migrations, model pulls, and schema generation are
deliberate commands you run — not things that silently happen on start-up.

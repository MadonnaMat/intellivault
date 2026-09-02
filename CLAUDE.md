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
- **Auth** (`app/auth/`) is passwordless WebAuthn passkeys (`py_webauthn`).
  Registration does **not** create a `users` row until a verified `finish`
  (inside a transaction, `INSERT ... ON CONFLICT`); the pending email/display
  name ride on the challenge. Emails are stored lowercased and matched
  case-insensitively (`lower(email)` unique index). Registration is
  first-come-first-served — there is no email-ownership check, so add email
  verification before treating an email as an identity claim.
  Ceremony challenges are stored in Postgres and consumed once, keyed by the
  short-lived `iv_ceremony` cookie; `store_challenge` also sweeps expired rows.
  A successful ceremony issues an opaque server-side session — random token,
  only its SHA-256 stored in `sessions`, carried in the `HttpOnly` `iv_session`
  cookie. All auth cookies get their Secure/SameSite/Domain flags from config
  (`app/auth/cookies.py`) — a split-domain deploy sets `SESSION_COOKIE_SAMESITE=none`
  + `SESSION_COOKIE_DOMAIN=.example.com`. `current_user` (a FastAPI dependency)
  resolves the session to a `SessionUser`; `sessions.user_id` is the ownerId
  every tenant-scoped query keys off. `/auth/me` clears a cookie that no longer
  resolves. Multi-line SQL lives in `app/auth/sql/*.sql` (embedded via
  `app.auth.statements.sql`). Frontend: `@simplewebauthn/browser` drives the
  browser API, `lib/api.ts` is the session-cookie fetch primitive, `middleware.ts`
  gates on cookie presence for signed-out visitors, and each protected page —
  plus `/login` and `/register` — re-checks `/auth/me` server-side (`lib/session.ts`).
- **Graph** (`app/graph/`) is the Neo4j knowledge graph: `Entity` nodes and
  `RELATED_TO` edges, each carrying `owner_id` (= `str(current_user.id)`) and
  `visibility` (`private`/`public`). Neo4j Community has no property-level RBAC,
  so **property-level security is enforced in every read's Cypher `WHERE`** —
  `visibility = 'public' OR owner_id = $owner_id` for nodes; edge + both
  endpoints for relationships. `tests/graph/test_cypher_predicate.py` fails any
  `cypher/*.cypher` that reads `:Entity` without that scoping + a `// SECURITY:`
  note. `PATCH /graph/entities/{id}/visibility` flips one node, or with
  `cascade=true` the whole caller-owned connected sub-graph (the
  private→public "merge", symmetric). `service.py` has exactly one
  `driver.session()` site (`_run`); one compound Cypher statement per call,
  atomic server-side. Frontend `/graph`: tables + a per-entity visibility
  `Switch`/cascade `Checkbox` + a Cytoscape.js diagram (`next/dynamic`,
  `ssr:false`) + a "Load sample graph" injector.
- **Migrations**: Postgres uses the `yoyo` CLI (plain SQL + `.rollback.sql` in
  `backend/migrations/`) — `make migrate` / `docker compose run --rm migrate`.
  Neo4j has no yoyo equivalent, so `app/graph/migrations.py` is a small
  stand-in: numbered `backend/graph_migrations/NNNN.name.cypher` (+
  `.rollback.cypher`), applied ids tracked as `(:_GraphMigration)` nodes —
  `make graph-migrate{,-down,-status}` / `docker compose run --rm graph-migrate`.
  Nothing runs either automatically.
- **SQL/Cypher that doesn't fit on one line** lives in its own `.sql` / `.cypher`
  file next to the code that runs it and is embedded from there (see
  `app/auth/sql/` + `app/auth/statements.py`, `app/graph/cypher/` +
  `app/graph/statements.py`), never inlined as a multi-line string literal.
- **Frontend API types** are generated from the FastAPI OpenAPI schema:
  `backend/scripts/dump_openapi.py` -> committed `openapi.json` ->
  `frontend/src/lib/api-schema.ts`. Never hand-edit either.
- **Tests use separate databases.** Postgres: `<db>_test` in the same instance
  (created by `docker/initdb`). Neo4j: a disposable `neo4j-test` service under the
  `test` compose profile — the graph integration tests
  (`tests/graph/test_integration.py`, `test_migrations.py`) hit it via
  `NEO4J_TEST_URI`/`NEO4J_TEST_PASSWORD` and self-skip when unreachable; the
  `graph_driver` fixture wipes + re-migrates per test. Never point
  unit/integration tests at the app databases.
- **`frontend/e2e/`** is the Playwright browser suite (`make e2e`, its own CI
  job) — it drives the real frontend + backend + Postgres + Neo4j, using a CDP
  virtual authenticator for the passkey ceremonies. It resets Postgres
  (`helpers/db.ts`) and the graph (`helpers/graph.ts`, over bolt) per test, so it
  needs a throwaway stack. `scripts/verify` stays the fast smoke check.
- Frontend components use **Ant Design**; all antd usage stays in client
  components (the RSC page is plain HTML). Interactive elements carry a
  `data-testid`; vitest and Playwright both query by testid.

## Commands

| Command | Does |
|---------|------|
| `make up` / `make verify` | bring the stack up / + smoke-check health + SSR |
| `make e2e` | Playwright browser suite against the full stack |
| `make lint` / `make test` | both sides |
| `make backend-lint` | ruff check + format, mypy --strict, radon |
| `make backend-test` | pytest (coverage gate 85%) |
| `make frontend-lint` | eslint + tsc --noEmit |
| `make frontend-test` | vitest |
| `make migrate` / `migrate-down` / `migrate-status` | yoyo (Postgres) |
| `make graph-migrate` / `graph-migrate-down` / `graph-migrate-status` | Neo4j graph schema |
| `make gen-api-types` / `check-api-types` | regenerate / verify the API contract |
| `make openapi` | rewrite `openapi.json` from the FastAPI app |

## Ethos

Explicit steps, not magic. Migrations, model pulls, and schema generation are
deliberate commands you run — not things that silently happen on start-up.

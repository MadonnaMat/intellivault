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
  hostnames (`postgres`, `neo4j`, `phoenix`, `redis`, `search-mcp`) for the
  `backend` / `agent-worker` containers. The agent stack adds `redis` (taskiq
  queue), `searxng` + `search-mcp` (web search MCP), and `agent-worker` (the
  taskiq worker, its own process). `docker-compose.e2e.yml` swaps Ollama +
  search-mcp for one `mock-ai` container for the Playwright suite.
- **Config** lives in `backend/app/config.py` (pydantic-settings). Secrets
  (`NEO4J_PASSWORD`, `DATABASE_URL`) are required — no hardcoded defaults. The
  repo-root `.env` (gitignored) feeds native runs; compose injects env directly.
- **`/health`** (`app/health/`) probes Postgres, Neo4j, Phoenix, Ollama, Redis
  and the search MCP concurrently, each with a 3s timeout, failures captured not
  raised, and the whole batch bounded by an overall deadline so a stuck probe
  can't hang it. It aggregates to `ok` / `degraded` / `down` and returns HTTP 503
  only when `down`. A failure of a **non-critical** dependency
  (`ServiceStatus.critical=False` — Phoenix, `redis`, `search-mcp`: only the
  agent worker needs the last two) or a missing Ollama model is `degraded` —
  still 200.
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
  endpoints for relationships. Creating a relationship requires the caller to own
  at least one endpoint, and a **public edge is only allowed between two public
  entities** (an edge can't be more visible than its endpoints) — a public
  request with a private endpoint is a 422. `tests/graph/test_cypher_predicate.py` (comments
  stripped) fails any `cypher/*.cypher` that touches `:Entity` without binding
  `owner_id` to `$owner_id` + a `// SECURITY:` note, and the tenant-visible
  reads (`list_*`/`get_*`) must carry the full `visibility = 'public' OR …`
  predicate. `PATCH /graph/entities/{id}/visibility` flips one node, or with
  `cascade=true` the whole caller-owned connected sub-graph (the private→public
  "merge", symmetric) — one `session.execute_write` transaction; `affected_ids`
  lists only entities that actually changed. Going **→ private** also demotes the
  caller's now-over-visible public edges on those nodes and **deletes** every
  edge on them the caller doesn't own (it would dangle from a node its owner can
  no longer see). `DELETE /graph/{entities,relationships}/{id}` (owner, or an
  endpoint owner for an edge). Single-statement ops go through the lone `_run`
  (`session.run`, atomic on the server); `list_graph` runs its two reads
  concurrently. Frontend `/graph`: tables (with delete) + a per-entity
  visibility `Switch`/cascade `Checkbox` + a Cytoscape.js diagram
  (`next/dynamic`, `ssr:false`) + a "Load sample graph" injector.
  Graph migration `0002` adds a **`CREATE VECTOR INDEX entity_embedding`** on
  `:Entity(embedding)` (768-d cosine, sized for `nomic-embed-text`);
  `service.set_entity_embedding` (owner-scoped) and `service.search_entities_by_vector`
  (`db.index.vector.queryNodes` + the same visibility predicate) back the agent's
  survey step. `test_cypher_predicate.py` also scans `queryNodes` files and treats
  `search_*` as a tenant-visible read.
- **Agent** (`app/agent/`) is the research loop: `POST /agent/runs` inserts a
  durable `agent_runs` row (Postgres) and enqueues a Redis job; a **separate
  `taskiq worker` process** (`agent-worker` container) runs a LangGraph pipeline
  — `plan → survey_graph → search → fetch → analyze → structure → commit` — and
  updates the row per node so `GET /agent/runs/{id}` shows live progress. The
  worker opens its own `WorkerInfra` (pool / driver / httpx / `ChatOllama` /
  `OllamaEmbeddings` / the SearXNG `search` tool from the MCP server) in
  `WORKER_STARTUP`. **`commit_node` writes only through `app.graph.service`**
  (`create_entity` / `create_relationship`, `visibility="private"`) — no new
  Cypher — so every tenant predicate holds; a service 404/422 on an edge goes to
  the run's `skipped`, never fatal. The batch is **not** atomic —
  `append_committed_*` records each write as it lands. `survey_graph_node` feeds
  the LLM a *bounded* digest: vector-search the topic (`agent_survey_max_entities`
  cap), falling back to lexical ranking. `fetch.guard_url` resolves every URL +
  redirect hop and refuses private / loopback / link-local / unresolvable hosts.
  The gateway process never imports langgraph (`enqueue_run` imports `tasks`
  lazily; `tests/agent/test_imports.py` guards it). Tests: unit with hand-rolled
  fakes; `tests/agent/test_integration.py` runs the real graph against
  `neo4j-test` with Ollama over `respx`; `frontend/e2e/agent.spec.ts` drives the
  full containerised loop with the **`mock-ai`** container (`docker-compose.e2e.yml`,
  CopilotKit aimock — chat + MCP; embeddings unmocked, which is fine since
  embedding is best-effort). `search_mcp.py` / `AGENT_SEARCH_MCP_*` /
  compose `search-mcp` are all named for `search` so a later non-search MCP gets
  its own module. Prompts are Markdown under `app/agent/prompts/` (loaded like
  the SQL). Interactive API surface: **Scalar at `/scalar`**, gated with
  `/docs`/`/redoc`/`/openapi.json` behind `settings.docs_enabled` (default true).
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
| `make e2e` | Playwright browser suite (adds `docker-compose.e2e.yml`: `mock-ai` + `agent-worker`) |
| `make agent-worker` | run the agent-loop taskiq worker natively (compose runs its own) |
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

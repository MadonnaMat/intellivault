# IntelliVault

A collaborative intelligence vault — a FastAPI gateway and Next.js frontend over a
Neo4j graph/vector store, Postgres for auth/credential metadata, Arize-Phoenix for
agent observability, and a local Ollama model server.

One-command bring-up, a `/health` endpoint that deeply probes every dependency,
passwordless WebAuthn passkey auth, a Neo4j knowledge graph of `Entity` nodes
and `RELATED_TO` edges (each with an owner + `private`/`public` visibility) with
a `/graph` UI, and an **agent loop**: `POST /agent/runs` with a research topic
and a separate taskiq worker runs a LangGraph graph (plan → survey the caller's
graph → search the web → fan out one reader per source → synthesize → structure
entities → self-critique → enrich from Wikipedia → commit to Neo4j as private
nodes → cross-link into the existing graph), with bounded retry cycles and an
optional human-review gate (`AGENT_REVIEW_REQUIRED`) before anything is written.
Full lint / type / complexity / test tooling on both sides.

## Architecture

| Piece      | Tech                                   | Notes |
|------------|----------------------------------------|-------|
| `backend/` | FastAPI, `uv`, pydantic-settings       | `/health` (deep) + `/health/live`; OTel traces to Phoenix |
| `frontend/`| Next.js 15 (App Router, TS), Ant Design | Server-renders `/health`, client Refresh button |
| Neo4j      | `neo4j:5.26-community`                  | graph + native vector index |
| Postgres   | `postgres:18-alpine`                   | user + auth/credential metadata; yoyo migrations |
| Phoenix    | `arizephoenix/phoenix`                 | agent observability UI on `:6006` |
| Ollama     | host-installed (GPU)                   | **not** in compose — see `scripts/ollama-dev` |
| Redis      | `redis:7-alpine`                       | taskiq queue for the agent loop |
| SearXNG + MCP | `searxng` + `search-mcp`            | the agent's web-search tool (streamable-HTTP MCP) |
| wikipedia-mcp | `mcp/wikipedia-mcp`                 | the agent's Wikipedia lookup tool (streamable-HTTP MCP) |
| taskiq-admin | `ghcr.io/taskiq-python/taskiq-admin` | job-queue dashboard on `:3300` (queued / started / finished / errored) |
| agent-worker | `build: ./backend`                  | `taskiq worker` — runs the LangGraph graph, its own process |

Ollama runs on the host so it can use the GPU; containers reach it at
`host.docker.internal:11434`. `scripts/ollama-dev` is the single control point for
that process and pulls the required models (`nomic-embed-text`, `qwen3:8b`).

## Prerequisites

- Docker + Docker Compose
- Node 22 and `pnpm` 10 (`corepack` or the standalone installer)
- `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Host Ollama (the scripts will install it) and, ideally, an NVIDIA GPU

## Quickstart

```bash
make up        # .env, host Ollama + models, compose --wait, migrations
make verify    # ^ plus assert /health is healthy and the frontend serves
```

Then open:

| URL                              | What |
|----------------------------------|------|
| http://localhost:3000            | frontend |
| http://localhost:8000/health     | deep health JSON |
| http://localhost:8000/docs       | API docs (`/scalar` for the interactive explorer) |
| http://localhost:7474            | Neo4j browser |
| http://localhost:6006            | Phoenix (agent-run traces) |
| http://localhost:3300            | taskiq-admin (agent job queue) — token `TASKIQ_ADMIN_TOKEN` |

## Development

```bash
make lint            # backend-lint + frontend-lint
make test            # backend-test + frontend-test
make migrate         # apply Postgres migrations   (migrate-down / migrate-status)
make graph-migrate   # apply Neo4j graph schema    (graph-migrate-down / -status)
make gen-api-types   # FastAPI schema -> frontend/src/lib/api-schema.ts
make test-db-up      # isolated Postgres test DB + disposable Neo4j (profile "test")
make agent-worker    # run the agent-loop taskiq worker natively (compose runs its own)
```

`make up` brings up the agent stack (Redis, SearXNG + `search-mcp`,
`wikipedia-mcp`, `taskiq-admin`, `agent-worker`) alongside everything else.
`make e2e` layers in
`docker-compose.e2e.yml`, which swaps the worker's Ollama + both MCPs for a
single `mock-ai` container so the whole loop runs with no GPU and no network.

Neo4j has no migration framework like yoyo; `backend/app/graph/migrations.py` is
a small numbered-Cypher runner that tracks applied migrations as nodes in the
graph. See [CLAUDE.md](CLAUDE.md).

Backend and frontend each have their own toolchain — see `backend/pyproject.toml`
and `frontend/package.json`. The frontend's TypeScript types for the API are
**generated** from the committed `openapi.json`; CI fails if they drift.

See [CLAUDE.md](CLAUDE.md) for the contribution workflow.

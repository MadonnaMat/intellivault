"""Application configuration, loaded from the environment via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values come from the process environment (docker-compose injects them) or
    a local ``.env`` file for native development. Defaults target a native run
    against ``docker compose up`` infrastructure on localhost.
    """

    model_config = SettingsConfigDict(
        # Native dev: the repo-root .env (backend runs from ./backend). In
        # docker-compose the environment is injected directly, so neither
        # file needs to exist.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "intellivault-backend"

    # Serve /docs, /redoc, /openapi.json and the Scalar API explorer at /scalar.
    # Same-origin, so /scalar's "try it out" carries the iv_session cookie. Set
    # false in production to close the interactive surface.
    docs_enabled: bool = True

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr  # required — supplied via environment / .env

    # --- Postgres ---
    # Full DSN (contains credentials) — required, supplied via environment /
    # the gitignored .env. Same value is consumed by the yoyo migration CLI.
    database_url: PostgresDsn
    # asyncpg pool bounds. min_size stays 0 so an unreachable Postgres surfaces
    # as postgres=down in /health rather than crashing start-up. max_size covers
    # health probes + every auth request handler.
    db_pool_min_size: int = 0
    db_pool_max_size: int = 20

    # --- Arize-Phoenix ---
    phoenix_collector_endpoint: str = "http://localhost:6006"
    # Set false to skip OTel/Phoenix wiring entirely (tests, offline dev).
    tracing_enabled: bool = True

    # --- Ollama (host-installed) ---
    ollama_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen3:8b"

    # --- Agent loop (Redis-backed taskiq queue; the worker runs as its own
    # process — see app/agent/). "memory://" swaps in taskiq's InMemoryBroker
    # for tests / offline dev. ---
    redis_url: str = "redis://localhost:6379/0"
    # Source fetching (agent/fetch.py). Every URL + redirect hop is resolved and
    # checked against private/loopback/link-local address space before connecting.
    agent_fetch_timeout: float = 10.0
    agent_fetch_max_redirects: int = 3
    agent_fetch_max_bytes: int = 2_000_000
    agent_source_char_limit: int = 12_000
    # Wikimedia (and others) 403 both an obvious bot UA *and* a generic browser
    # string — their policy (w.wiki/4wJS) wants a descriptive UA with a contact
    # URL. Override per deployment with a real contact.
    agent_fetch_user_agent: str = (
        "IntelliVault-Agent/0.1 (+https://github.com/MadonnaMat/intellivault) python-httpx"
    )
    # The web-search MCP server (SearXNG, streamable-HTTP). Named *_search_* so
    # each MCP server gets its own setting. Native dev points at a locally-run
    # container; compose overrides these to the in-network services.
    agent_search_mcp_url: str = "http://localhost:8770/mcp"
    # The Wikipedia MCP server — authoritative entity summaries + related topics,
    # used by the `lookup` node to enrich the drafted entities.
    agent_wikipedia_mcp_url: str = "http://localhost:8771/mcp"
    # Passed to ChatOllama — 0.0 keeps structure/plan extraction deterministic.
    agent_llm_temperature: float = 0.0
    # Per-call timeouts so a hung model / MCP server can't stall a run forever,
    # and an overall per-run deadline enforced by the worker. All in seconds.
    agent_llm_timeout: float = 240.0
    agent_mcp_timeout: float = 30.0
    agent_run_timeout: float = 2400.0
    # Passed to ChatOllama as `reasoning` — False disables a thinking model's
    # (qwen3, deepseek-r1) `<think>` block, which roughly halves latency on a
    # local model at a small quality cost. Set true if the box is fast.
    agent_llm_reasoning: bool = False
    # Cap on source pages a single run fetches (across all its search queries).
    agent_max_sources: int = 5
    # Cap on draft entities the `lookup` node enriches from Wikipedia — each one
    # is 3 sequential MCP round trips, so an unbounded list (e.g. "every actor
    # in <show>") can grind for many minutes.
    agent_lookup_max_entities: int = 20
    # Cap on entities from the caller's visible graph fed to the LLM as context
    # (ranked by relevance to the topic, then recency) — the whole graph would
    # blow a small model's context and grows unbounded with the public graph.
    agent_survey_max_entities: int = 150
    # Runs the worker processes concurrently (taskiq `--max-async-tasks`).
    agent_worker_concurrency: int = 4
    # Bounded LangGraph cycles: how many times `broaden_queries` may re-search
    # when a round finds nothing, and how many times `critique` may bounce a
    # weak draft back to `structure`.
    agent_search_retries: int = 1
    agent_critique_retries: int = 1
    # When true, a run pauses after `lookup` at status=awaiting_review; the
    # drafted entities are only committed once POST /agent/runs/{id}/review
    # approves them.
    agent_review_required: bool = True
    # taskiq-admin dashboard (optional): when `taskiq_admin_url` is set, the
    # broker reports every task's lifecycle (queued / started / finished / error)
    # to it. Empty (the default) = no reporting. The token must match the
    # dashboard container's TASKIQ_ADMIN_API_TOKEN.
    taskiq_admin_url: str = ""
    taskiq_admin_token: str = ""

    # --- CORS ---
    # Comma-separated list of allowed frontend origins. NoDecode keeps
    # pydantic-settings from JSON-parsing the env value so the validator
    # below can split it.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000"],
        validation_alias=AliasChoices("cors_origins", "CORS_ORIGINS"),
    )

    # --- Auth / WebAuthn ---
    # The Relying Party id (an effective domain, no scheme/port) and the exact
    # origin the browser ceremony runs on. Dev defaults target the Next.js app
    # on localhost; real deploys override both.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "IntelliVault"
    webauthn_origin: str = "http://localhost:3000"
    # Session lifetime and cookie flags. Defaults suit plain-http localhost where
    # the frontend and backend share a hostname. A split-domain deployment sets
    # secure=true, samesite=none, and domain=.example.com so the browser sends
    # the cookie to both the app and the API host.
    session_ttl_hours: int = 720
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_domain: str | None = None

    @field_validator("session_cookie_domain", mode="before")
    @classmethod
    def _blank_domain_is_none(cls, value: object) -> object:
        """Treat an empty env value the same as unset."""
        return value or None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string (from env) as well as a real list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def database_dsn(self) -> str:
        """The application database DSN as a plain string (for asyncpg / yoyo)."""
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

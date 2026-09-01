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

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr  # required — supplied via environment / .env

    # --- Postgres ---
    # Full DSN (contains credentials) — required, supplied via environment /
    # the gitignored .env. Same value is consumed by the yoyo migration CLI.
    database_url: PostgresDsn

    # --- Arize-Phoenix ---
    phoenix_collector_endpoint: str = "http://localhost:6006"
    # Set false to skip OTel/Phoenix wiring entirely (tests, offline dev).
    tracing_enabled: bool = True

    # --- Ollama (host-installed) ---
    ollama_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen3:8b"

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

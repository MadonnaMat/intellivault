"""Application configuration, loaded from the environment via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "intellivault"
    postgres_password: SecretStr  # required — supplied via environment / .env
    postgres_db: str = "intellivault"

    # --- Arize-Phoenix ---
    phoenix_collector_endpoint: str = "http://localhost:6006"

    # --- Ollama (host-installed) ---
    ollama_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen3:8b"

    # --- CORS ---
    # Comma-separated list of allowed frontend origins.
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        validation_alias=AliasChoices("cors_origins", "CORS_ORIGINS"),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string (from .env) as well as a real list."""
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

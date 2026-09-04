"""app.agent.embeddings — build_embedder wiring."""

from __future__ import annotations

from langchain_ollama import OllamaEmbeddings

from app.agent.embeddings import build_embedder
from app.config import Settings


def test_build_embedder_wires_settings() -> None:
    settings = Settings(
        _env_file=None,
        NEO4J_PASSWORD="n",
        DATABASE_URL="postgresql://u:p@localhost:5432/db",
        OLLAMA_URL="http://ollama.test:11434",
        OLLAMA_EMBED_MODEL="nomic-embed-text",
    )
    embedder = build_embedder(settings)
    assert isinstance(embedder, OllamaEmbeddings)
    assert embedder.model == "nomic-embed-text"
    assert embedder.base_url == "http://ollama.test:11434"

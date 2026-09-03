"""The Ollama embedding model the agent uses to embed entities + survey queries."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings

from app.config import Settings


def build_embedder(settings: Settings) -> Embeddings:
    return OllamaEmbeddings(
        base_url=settings.ollama_url,
        model=settings.ollama_embed_model,
        client_kwargs={"timeout": settings.agent_llm_timeout},
    )

"""Process-wide clients for the worker (``WorkerInfra``) and the per-run bundle
the LangGraph nodes close over (``AgentDeps``).

The worker has no FastAPI ``app.state`` — it opens its own asyncpg pool, Neo4j
driver, httpx client, Ollama model and MCP search tool once at ``WORKER_STARTUP``
and closes them at ``WORKER_SHUTDOWN``.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg
import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.agent.embeddings import build_embedder
from app.agent.fetch import build_http_client
from app.agent.llm import build_chat_model
from app.agent.mcp import load_search_tool
from app.config import Settings


@dataclass(slots=True)
class WorkerInfra:
    """Long-lived clients shared across every run the worker processes."""

    settings: Settings
    pg_pool: asyncpg.Pool
    neo4j_driver: AsyncDriver
    http_client: httpx.AsyncClient
    chat_model: BaseChatModel
    embedder: Embeddings
    search_tool: BaseTool

    async def aclose(self) -> None:
        await self.http_client.aclose()
        await self.neo4j_driver.close()
        await self.pg_pool.close()


async def build_worker_infra(settings: Settings) -> WorkerInfra:
    pg_pool = await asyncpg.create_pool(
        settings.database_dsn, min_size=0, max_size=settings.db_pool_max_size
    )
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    return WorkerInfra(
        settings=settings,
        pg_pool=pg_pool,
        neo4j_driver=neo4j_driver,
        http_client=build_http_client(settings),
        chat_model=build_chat_model(settings),
        embedder=build_embedder(settings),
        search_tool=await load_search_tool(settings),
    )


@dataclass(slots=True)
class AgentDeps:
    """Everything a node needs that isn't per-run scalar state."""

    settings: Settings
    pool: asyncpg.Pool
    driver: AsyncDriver
    http_client: httpx.AsyncClient
    chat_model: BaseChatModel
    embedder: Embeddings
    search_tool: BaseTool

    @classmethod
    def from_infra(cls, infra: WorkerInfra) -> AgentDeps:
        return cls(
            settings=infra.settings,
            pool=infra.pg_pool,
            driver=infra.neo4j_driver,
            http_client=infra.http_client,
            chat_model=infra.chat_model,
            embedder=infra.embedder,
            search_tool=infra.search_tool,
        )

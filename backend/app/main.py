"""IntelliVault FastAPI gateway — application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncGraphDatabase
from scalar_fastapi import add_scalar_reference

from app import observability
from app.agent import agent_router
from app.auth import auth_router
from app.config import Settings, get_settings
from app.graph import graph_router
from app.health import health_router
from app.health.checks import CHECK_TIMEOUT_SECONDS, HealthProbes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open shared clients for downstream services, and close them on shutdown."""
    settings: Settings = app.state.settings

    # min_size=0 (default): don't open a connection at startup — an unreachable
    # Postgres should surface as postgres=down in /health, not crash the process.
    pg_pool = await asyncpg.create_pool(
        settings.database_dsn,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        # Keep the driver's own waits within range of the health-probe timeout
        # so a cancelled probe can't leave a long-running acquisition behind.
        connection_timeout=CHECK_TIMEOUT_SECONDS,
        connection_acquisition_timeout=CHECK_TIMEOUT_SECONDS,
    )
    http_client = httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS)

    # Shared clients live on app.state; request handlers reach them via the
    # app.db.get_pool / app.graph.db.get_driver dependencies, and the health
    # probes read the same objects.
    app.state.pg_pool = pg_pool
    app.state.neo4j_driver = neo4j_driver
    app.state.health_probes = HealthProbes(
        settings=settings,
        pg_pool=pg_pool,
        neo4j_driver=neo4j_driver,
        http_client=http_client,
    )
    try:
        yield
    finally:
        await http_client.aclose()
        await neo4j_driver.close()
        await pg_pool.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()

    # docs_enabled=false closes /docs, /redoc, /openapi.json and /scalar together.
    docs = settings.docs_enabled
    app = FastAPI(
        title="IntelliVault",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    observability.setup(app, settings)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(graph_router)
    app.include_router(agent_router)

    if docs:
        # Scalar API explorer at /scalar — served by us, so "try it out" is
        # same-origin and carries the iv_session cookie with no CORS dance.
        add_scalar_reference(app)

    return app


# Run with: uvicorn app.main:create_app --factory
# (no module-level instance, so importing this module never needs settings).

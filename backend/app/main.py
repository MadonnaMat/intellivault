"""IntelliVault FastAPI gateway — application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncGraphDatabase

from app import observability
from app.config import Settings, get_settings
from app.health import health_router
from app.health.checks import CHECK_TIMEOUT_SECONDS, HealthProbes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open shared clients for downstream services, and close them on shutdown."""
    settings: Settings = app.state.settings

    pg_pool = await asyncpg.create_pool(settings.database_dsn, min_size=1, max_size=5)
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    http_client = httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS)

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

    app = FastAPI(title="IntelliVault", version="0.1.0", lifespan=lifespan)
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

    return app


app = create_app()

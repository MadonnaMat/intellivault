"""app.agent.deps — AgentDeps.from_infra + WorkerInfra.aclose ordering.

build_worker_infra (which opens real clients) is covered in the worker slice.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.agent.deps import AgentDeps, WorkerInfra
from app.config import Settings

_SETTINGS = Settings(
    _env_file=None, NEO4J_PASSWORD="n", DATABASE_URL="postgresql://u:p@localhost:5432/db"
)


class _Recorder:
    def __init__(self, log: list[str], label: str) -> None:
        self._log = log
        self._label = label

    async def aclose(self) -> None:
        self._log.append(self._label)

    async def close(self) -> None:
        self._log.append(self._label)


def _infra(log: list[str]) -> WorkerInfra:
    return WorkerInfra(
        settings=_SETTINGS,
        pg_pool=cast(Any, _Recorder(log, "pg")),
        neo4j_driver=cast(Any, _Recorder(log, "neo4j")),
        http_client=cast(Any, _Recorder(log, "http")),
        chat_model=cast(Any, object()),
        embedder=cast(Any, object()),
        search_tool=cast(Any, object()),
        wikipedia_tools={},
    )


async def test_aclose_closes_clients_in_reverse_order() -> None:
    log: list[str] = []
    await _infra(log).aclose()
    assert log == ["http", "neo4j", "pg"]


async def test_build_worker_infra_opens_every_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent import deps

    async def _fake_pool(*_a: object, **_k: object) -> str:
        return "pool"

    async def _fake_tool(_s: object) -> str:
        return "tool"

    async def _wiki() -> dict[str, int]:
        return {"w": 1}

    monkeypatch.setattr("app.agent.deps.asyncpg.create_pool", _fake_pool)
    monkeypatch.setattr("app.agent.deps.AsyncGraphDatabase.driver", lambda *_a, **_k: "driver")
    monkeypatch.setattr(deps, "build_http_client", lambda _s: "http")
    monkeypatch.setattr(deps, "build_chat_model", lambda _s: "chat")
    monkeypatch.setattr(deps, "build_embedder", lambda _s: "embed")
    monkeypatch.setattr(deps, "load_search_tool", _fake_tool)
    monkeypatch.setattr(deps, "load_wikipedia_tools", lambda _s: _wiki())

    infra = await deps.build_worker_infra(_SETTINGS)
    got: list[object] = [
        infra.pg_pool,
        infra.neo4j_driver,
        infra.http_client,
        infra.chat_model,
        infra.embedder,
        infra.search_tool,
        infra.wikipedia_tools,
    ]
    assert got == ["pool", "driver", "http", "chat", "embed", "tool", {"w": 1}]


def test_from_infra_shares_the_worker_clients() -> None:
    infra = _infra([])
    deps = AgentDeps.from_infra(infra)
    assert deps.pool is infra.pg_pool
    assert deps.driver is infra.neo4j_driver
    assert deps.http_client is infra.http_client
    assert deps.chat_model is infra.chat_model
    assert deps.embedder is infra.embedder
    assert deps.search_tool is infra.search_tool
    assert deps.wikipedia_tools is infra.wikipedia_tools

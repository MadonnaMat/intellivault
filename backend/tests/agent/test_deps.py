"""app.agent.deps — AgentDeps.from_infra + WorkerInfra.aclose ordering.

build_worker_infra (which opens real clients) is covered in the worker slice.
"""

from __future__ import annotations

from typing import Any, cast

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
        search_tool=cast(Any, object()),
    )


async def test_aclose_closes_clients_in_reverse_order() -> None:
    log: list[str] = []
    await _infra(log).aclose()
    assert log == ["http", "neo4j", "pg"]


def test_from_infra_shares_the_worker_clients() -> None:
    infra = _infra([])
    deps = AgentDeps.from_infra(infra)
    assert deps.pool is infra.pg_pool
    assert deps.driver is infra.neo4j_driver
    assert deps.http_client is infra.http_client
    assert deps.chat_model is infra.chat_model
    assert deps.search_tool is infra.search_tool

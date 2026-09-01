"""Unit tests for auth service error branches that are awkward to reach over HTTP."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.auth import service
from app.auth.schemas import SessionUser, UpdateAccountRequest
from app.config import Settings

_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
)
_USER = SessionUser(id=uuid4(), email="a@b.com", display_name="Ada")


class FakePool:
    def __init__(self, *, fetchval: Any = None, fetchrow: Any = None) -> None:
        self._fetchval = fetchval
        self._fetchrow = fetchrow
        self.calls: list[str] = []

    async def execute(self, query: str, *_: Any) -> str:
        self.calls.append(query)
        return "OK"

    async def fetchval(self, query: str, *_: Any) -> Any:
        self.calls.append(query)
        return self._fetchval() if callable(self._fetchval) else self._fetchval

    async def fetchrow(self, query: str, *_: Any) -> Any:
        self.calls.append(query)
        if callable(self._fetchrow):
            return self._fetchrow()
        return self._fetchrow


def _pool(**kwargs: Any) -> Any:
    return FakePool(**kwargs)


@pytest.mark.asyncio
async def test_finish_registration_without_pending_user() -> None:
    with pytest.raises(HTTPException) as exc:
        await service.finish_registration(_pool(), _SETTINGS, b"c", None, {})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_finish_registration_rejects_junk_attestation() -> None:
    with pytest.raises(HTTPException) as exc:
        await service.finish_registration(
            _pool(), _SETTINGS, b"c", _USER.id, {"not": "a credential"}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_finish_login_rejects_malformed_response() -> None:
    with pytest.raises(HTTPException) as exc:
        await service.finish_login(_pool(), _SETTINGS, b"c", {"no": "rawId"})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_credential_not_found() -> None:
    pool = _pool(fetchval=iter([2, None]).__next__)
    with pytest.raises(HTTPException) as exc:
        await service.delete_credential(pool, _USER, uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_account_conflict_maps_to_409() -> None:
    def _raise() -> Any:
        raise asyncpg.UniqueViolationError("dup")

    with pytest.raises(HTTPException) as exc:
        await service.update_account(
            _pool(fetchrow=_raise), _USER, UpdateAccountRequest(email="x@y.com")
        )
    assert exc.value.status_code == 409

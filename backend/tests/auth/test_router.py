"""End-to-end auth-flow tests driven by a simulated authenticator.

Runs against the real test database (``DATABASE_URL`` -> ``intellivault_test``,
set in conftest) and self-skips when it is unreachable.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from soft_webauthn import SoftWebauthnDevice

from app.main import create_app
from tests.helpers.webauthn import (
    authentication_to_json,
    options_to_soft,
    registration_to_json,
)

TEST_DSN = os.environ["DATABASE_URL"]
ORIGIN = "http://localhost:3000"
_TABLES = "users, sessions, webauthn_credentials, webauthn_challenges"


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(TEST_DSN)


def _reachable() -> bool:
    async def _try() -> bool:
        try:
            conn = await _connect()
        except (OSError, asyncpg.PostgresError):
            return False
        await conn.close()
        return True

    return asyncio.run(_try())


pytestmark = pytest.mark.skipif(not _reachable(), reason="test database not reachable")


async def _truncate() -> None:
    conn = await _connect()
    try:
        await conn.execute(f"TRUNCATE {_TABLES} CASCADE")
    finally:
        await conn.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    asyncio.run(_truncate())
    with TestClient(create_app()) as test_client:
        yield test_client


# --- ceremony helpers ------------------------------------------------------


def _register(
    client: TestClient, device: SoftWebauthnDevice, email: str, display_name: str = "Ada"
) -> Any:
    options = client.post(
        "/auth/register/begin", json={"email": email, "display_name": display_name}
    )
    assert options.status_code == 200, options.text
    attestation = device.create(options_to_soft(options.json()), ORIGIN)
    return client.post("/auth/register/finish", json=registration_to_json(attestation))


def _login(client: TestClient, device: SoftWebauthnDevice) -> Any:
    options = client.post("/auth/login/begin", json={})
    assert options.status_code == 200, options.text
    assertion = device.get(options_to_soft(options.json()), ORIGIN)
    return client.post("/auth/login/finish", json=authentication_to_json(assertion))


def _add_passkey(client: TestClient, device: SoftWebauthnDevice, name: str) -> Any:
    options = client.post("/auth/credentials/begin")
    assert options.status_code == 200, options.text
    attestation = device.create(options_to_soft(options.json()), ORIGIN)
    return client.post(
        "/auth/credentials/finish",
        json={"name": name, "credential": registration_to_json(attestation)},
    )


# --- tests ---------------------------------------------------------------


def test_register_login_logout(client: TestClient) -> None:
    device = SoftWebauthnDevice()

    registered = _register(client, device, "ada@example.com")
    assert registered.status_code == 200, registered.text
    body = registered.json()
    assert body["email"] == "ada@example.com"
    assert body["display_name"] == "Ada"

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401

    logged_in = _login(client, device)
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["email"] == "ada@example.com"
    assert client.get("/auth/me").status_code == 200


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    assert _register(client, SoftWebauthnDevice(), "dup@example.com").status_code == 200
    client.post("/auth/logout")
    again = client.post(
        "/auth/register/begin", json={"email": "dup@example.com", "display_name": "Ada"}
    )
    assert again.status_code == 409


def test_login_with_unknown_passkey(client: TestClient) -> None:
    _register(client, SoftWebauthnDevice(), "known@example.com")
    client.post("/auth/logout")

    stranger = SoftWebauthnDevice()
    stranger.cred_init("localhost", b"nobody")  # a passkey the server never stored
    options = client.post("/auth/login/begin", json={})
    assertion = stranger.get(options_to_soft(options.json()), ORIGIN)
    result = client.post("/auth/login/finish", json=authentication_to_json(assertion))
    assert result.status_code == 401


def test_missing_ceremony_cookie(client: TestClient) -> None:
    device = SoftWebauthnDevice()
    options = client.post(
        "/auth/register/begin", json={"email": "x@example.com", "display_name": "X"}
    )
    attestation = device.create(options_to_soft(options.json()), ORIGIN)
    client.cookies.delete("iv_ceremony")
    finished = client.post("/auth/register/finish", json=registration_to_json(attestation))
    assert finished.status_code == 400


def test_add_passkey_then_login_with_it(client: TestClient) -> None:
    first = SoftWebauthnDevice()
    _register(client, first, "multi@example.com")

    second = SoftWebauthnDevice()
    added = _add_passkey(client, second, "Work laptop")
    assert added.status_code == 200, added.text
    assert added.json()["name"] == "Work laptop"

    assert len(client.get("/auth/credentials").json()) == 2

    client.post("/auth/logout")
    assert _login(client, second).status_code == 200


def test_update_account(client: TestClient) -> None:
    _register(client, SoftWebauthnDevice(), "old@example.com", "Old Name")

    updated = client.patch(
        "/auth/me", json={"email": "new@example.com", "display_name": "New Name"}
    )
    assert updated.status_code == 200
    assert updated.json()["email"] == "new@example.com"
    assert updated.json()["display_name"] == "New Name"

    after = client.get("/auth/me").json()
    assert after["email"] == "new@example.com"
    assert after["display_name"] == "New Name"


def test_update_account_rejects_taken_email(client: TestClient) -> None:
    _register(client, SoftWebauthnDevice(), "one@example.com")
    client.post("/auth/logout")
    _register(client, SoftWebauthnDevice(), "two@example.com")

    clash = client.patch("/auth/me", json={"email": "one@example.com"})
    assert clash.status_code == 409


def test_cannot_delete_last_passkey(client: TestClient) -> None:
    _register(client, SoftWebauthnDevice(), "solo@example.com")
    credentials = client.get("/auth/credentials").json()
    only = credentials[0]["id"]

    assert client.delete(f"/auth/credentials/{only}").status_code == 409

    second = SoftWebauthnDevice()
    _add_passkey(client, second, "Second")
    assert client.delete(f"/auth/credentials/{only}").status_code == 204
    assert len(client.get("/auth/credentials").json()) == 1

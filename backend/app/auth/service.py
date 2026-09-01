"""WebAuthn ceremony orchestration + the SQL behind the auth routes.

Each function is one step of a ceremony or one account operation; the router
stays a thin HTTP shell over these. Multi-line SQL lives in ``app/auth/sql/``.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.auth.ceremony import store_challenge
from app.auth.schemas import (
    AddPasskeyFinishRequest,
    CeremonyOptions,
    CeremonyResponse,
    CredentialSummary,
    RegisterBeginRequest,
    SessionUser,
    UpdateAccountRequest,
)
from app.auth.sessions import issue_session
from app.auth.statements import sql
from app.config import Settings

_CONFLICT = status.HTTP_409_CONFLICT
_UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED
_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


def _summary(row: asyncpg.Record) -> CredentialSummary:
    return CredentialSummary(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        transports=list(row["transports"]),
    )


async def _descriptors(pool: asyncpg.Pool, user_id: UUID) -> list[PublicKeyCredentialDescriptor]:
    rows = await pool.fetch(
        "SELECT credential_id FROM webauthn_credentials WHERE user_id = $1", user_id
    )
    return [PublicKeyCredentialDescriptor(id=row["credential_id"]) for row in rows]


def _options_dict(options: Any) -> CeremonyOptions:
    parsed: CeremonyOptions = json.loads(options_to_json(options))
    return parsed


def _registration_options(
    settings: Settings,
    *,
    user_id: UUID,
    email: str,
    display_name: str,
    exclude: list[PublicKeyCredentialDescriptor],
) -> Any:
    return generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=email,
        user_id=user_id.bytes,
        user_display_name=display_name,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )


async def _user(pool: asyncpg.Pool, user_id: UUID) -> SessionUser:
    row = await pool.fetchrow("SELECT id, email, display_name FROM users WHERE id = $1", user_id)
    assert row is not None
    return SessionUser(id=row["id"], email=row["email"], display_name=row["display_name"])


# --- registration ----------------------------------------------------------


async def begin_registration(
    pool: asyncpg.Pool, settings: Settings, req: RegisterBeginRequest
) -> tuple[CeremonyOptions, UUID]:
    row = await pool.fetchrow(sql("user_with_credential_count"), req.email)
    if row is not None and row["credentials"] > 0:
        raise HTTPException(_CONFLICT, "An account with that email already exists")

    if row is not None:
        user_id: UUID = row["id"]
        await pool.execute(
            "UPDATE users SET display_name = $2 WHERE id = $1", user_id, req.display_name
        )
    else:
        user_id = await pool.fetchval(
            "INSERT INTO users (email, display_name) VALUES ($1, $2) RETURNING id",
            req.email,
            req.display_name,
        )

    options = _registration_options(
        settings, user_id=user_id, email=req.email, display_name=req.display_name, exclude=[]
    )
    challenge_id = await store_challenge(pool, options.challenge, user_id)
    return _options_dict(options), challenge_id


async def _store_credential(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    challenge: bytes,
    settings: Settings,
    credential: CeremonyResponse,
    name: str,
) -> UUID:
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            require_user_verification=False,
        )
    except (WebAuthnException, KeyError, ValueError) as exc:
        raise HTTPException(_BAD_REQUEST, "Passkey registration failed") from exc

    transports = credential.get("response", {}).get("transports") or []
    try:
        new_id: UUID = await pool.fetchval(
            sql("insert_credential"),
            user_id,
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            list(transports),
            verified.aaguid,
            name,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(_CONFLICT, "That passkey is already registered") from exc
    return new_id


async def finish_registration(
    pool: asyncpg.Pool,
    settings: Settings,
    challenge: bytes,
    user_id: UUID | None,
    credential: CeremonyResponse,
) -> tuple[SessionUser, str]:
    if user_id is None:
        raise HTTPException(_BAD_REQUEST, "No registration in progress")
    await _store_credential(
        pool,
        user_id=user_id,
        challenge=challenge,
        settings=settings,
        credential=credential,
        name="Passkey",
    )
    user = await _user(pool, user_id)
    token = await issue_session(pool, user.id, settings)
    return user, token


# --- login ---------------------------------------------------------------


async def begin_login(pool: asyncpg.Pool, settings: Settings) -> tuple[CeremonyOptions, UUID]:
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_id = await store_challenge(pool, options.challenge, None)
    return _options_dict(options), challenge_id


async def finish_login(
    pool: asyncpg.Pool, settings: Settings, challenge: bytes, credential: CeremonyResponse
) -> tuple[SessionUser, str]:
    try:
        raw_id = base64url_to_bytes(credential["rawId"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(_BAD_REQUEST, "Malformed passkey response") from exc

    row = await pool.fetchrow(sql("credential_with_user"), raw_id)
    if row is None:
        raise HTTPException(_UNAUTHORIZED, "Unknown passkey")

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
            require_user_verification=False,
        )
    except (WebAuthnException, KeyError, ValueError) as exc:
        raise HTTPException(_UNAUTHORIZED, "Passkey verification failed") from exc

    await pool.execute(
        "UPDATE webauthn_credentials SET sign_count = $1, last_used_at = now() WHERE id = $2",
        verified.new_sign_count,
        row["id"],
    )
    user = SessionUser(id=row["user_id"], email=row["email"], display_name=row["display_name"])
    token = await issue_session(pool, user.id, settings)
    return user, token


# --- account management -------------------------------------------------


async def begin_add_passkey(
    pool: asyncpg.Pool, settings: Settings, user: SessionUser
) -> tuple[CeremonyOptions, UUID]:
    options = _registration_options(
        settings,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        exclude=await _descriptors(pool, user.id),
    )
    challenge_id = await store_challenge(pool, options.challenge, user.id)
    return _options_dict(options), challenge_id


async def finish_add_passkey(
    pool: asyncpg.Pool,
    settings: Settings,
    challenge: bytes,
    user_id: UUID | None,
    user: SessionUser,
    req: AddPasskeyFinishRequest,
) -> CredentialSummary:
    if user_id != user.id:
        raise HTTPException(_BAD_REQUEST, "No passkey registration in progress")
    new_id = await _store_credential(
        pool,
        user_id=user.id,
        challenge=challenge,
        settings=settings,
        credential=req.credential,
        name=req.name,
    )
    row = await pool.fetchrow(sql("credential_summary_by_id"), new_id)
    assert row is not None
    return _summary(row)


async def update_account(
    pool: asyncpg.Pool, user: SessionUser, req: UpdateAccountRequest
) -> SessionUser:
    email = req.email or user.email
    display_name = req.display_name or user.display_name
    try:
        row = await pool.fetchrow(sql("update_account"), user.id, email, display_name)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(_CONFLICT, "That email is already in use") from exc
    assert row is not None
    return SessionUser(id=row["id"], email=row["email"], display_name=row["display_name"])


async def list_credentials(pool: asyncpg.Pool, user: SessionUser) -> list[CredentialSummary]:
    rows = await pool.fetch(sql("list_credentials"), user.id)
    return [_summary(row) for row in rows]


async def delete_credential(pool: asyncpg.Pool, user: SessionUser, credential_id: UUID) -> None:
    total = await pool.fetchval(
        "SELECT count(*) FROM webauthn_credentials WHERE user_id = $1", user.id
    )
    if total <= 1:
        raise HTTPException(_CONFLICT, "You must keep at least one passkey")
    deleted = await pool.fetchval(
        "DELETE FROM webauthn_credentials WHERE id = $1 AND user_id = $2 RETURNING id",
        credential_id,
        user.id,
    )
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passkey not found")

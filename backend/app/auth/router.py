"""Auth routes: passkey registration, passkey login, sessions, account."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.ceremony import (
    CEREMONY_COOKIE,
    Challenge,
    clear_ceremony_cookie,
    pop_challenge,
    set_ceremony_cookie,
)
from app.auth.dependencies import current_user, current_user_optional
from app.auth.schemas import (
    AddPasskeyFinishRequest,
    CeremonyOptions,
    CeremonyResponse,
    CredentialSummary,
    RegisterBeginRequest,
    SessionUser,
    UpdateAccountRequest,
)
from app.auth.service import (
    begin_add_passkey,
    begin_login,
    begin_registration,
    delete_credential,
    finish_add_passkey,
    finish_login,
    finish_registration,
    list_credentials,
    update_account,
)
from app.auth.sessions import (
    SESSION_COOKIE,
    clear_session_cookie,
    revoke_session,
    set_session_cookie,
)
from app.config import Settings, get_settings
from app.db import get_pool

router = APIRouter(prefix="/auth", tags=["auth"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Config = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[SessionUser, Depends(current_user)]

_HTTP_400 = status.HTTP_400_BAD_REQUEST


async def _pop(pool: asyncpg.Pool, request: Request) -> Challenge:
    challenge = await pop_challenge(pool, request.cookies.get(CEREMONY_COOKIE))
    if challenge is None:
        raise HTTPException(_HTTP_400, "Ceremony expired or missing — start again")
    return challenge


@router.post("/register/begin")
async def register_begin(
    req: RegisterBeginRequest, response: Response, pool: Pool, settings: Config
) -> CeremonyOptions:
    options, challenge_id = await begin_registration(pool, settings, req)
    set_ceremony_cookie(response, challenge_id, settings)
    return options


@router.post("/register/finish")
async def register_finish(
    credential: CeremonyResponse,
    request: Request,
    response: Response,
    pool: Pool,
    settings: Config,
) -> SessionUser:
    ceremony = await _pop(pool, request)
    user, token = await finish_registration(
        pool, settings, ceremony.challenge, ceremony.email, ceremony.display_name, credential
    )
    clear_ceremony_cookie(response, settings)
    set_session_cookie(response, token, settings)
    return user


@router.post("/login/begin")
async def login_begin(response: Response, pool: Pool, settings: Config) -> CeremonyOptions:
    options, challenge_id = await begin_login(pool, settings)
    set_ceremony_cookie(response, challenge_id, settings)
    return options


@router.post("/login/finish")
async def login_finish(
    credential: CeremonyResponse,
    request: Request,
    response: Response,
    pool: Pool,
    settings: Config,
) -> SessionUser:
    ceremony = await _pop(pool, request)
    user, token = await finish_login(pool, settings, ceremony.challenge, credential)
    clear_ceremony_cookie(response, settings)
    set_session_cookie(response, token, settings)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, pool: Pool, settings: Config) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await revoke_session(pool, token)
    clear_session_cookie(response, settings)


@router.get("/me")
async def me(
    response: Response,
    settings: Config,
    user: Annotated[SessionUser | None, Depends(current_user_optional)],
) -> SessionUser:
    if user is None:
        # Proactively drop a cookie that no longer resolves so the browser stops
        # replaying it on every page load.
        clear_session_cookie(response, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


@router.patch("/me")
async def patch_me(req: UpdateAccountRequest, user: CurrentUser, pool: Pool) -> SessionUser:
    return await update_account(pool, user, req)


@router.get("/credentials")
async def get_credentials(user: CurrentUser, pool: Pool) -> list[CredentialSummary]:
    return await list_credentials(pool, user)


@router.post("/credentials/begin")
async def add_passkey_begin(
    user: CurrentUser, response: Response, pool: Pool, settings: Config
) -> CeremonyOptions:
    options, challenge_id = await begin_add_passkey(pool, settings, user)
    set_ceremony_cookie(response, challenge_id, settings)
    return options


@router.post("/credentials/finish")
async def add_passkey_finish(
    req: AddPasskeyFinishRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    pool: Pool,
    settings: Config,
) -> CredentialSummary:
    ceremony = await _pop(pool, request)
    summary = await finish_add_passkey(
        pool, settings, ceremony.challenge, ceremony.user_id, user, req
    )
    clear_ceremony_cookie(response, settings)
    return summary


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_credential(credential_id: UUID, user: CurrentUser, pool: Pool) -> None:
    await delete_credential(pool, user, credential_id)

"""Chat route: passes conversation turns through to Ollama, one AssistantTransport
turn (``POST /chat``) at a time. Speaks assistant-ui's AssistantTransport protocol
via ``assistant_stream`` — see ``app/chat/service.py`` for the turn logic.
"""

from __future__ import annotations

from typing import Annotated

import asyncpg
import httpx
from assistant_stream import RunController, create_run
from assistant_stream.serialization import AssistantTransportResponse
from fastapi import APIRouter, Depends

from app.auth.dependencies import current_user
from app.auth.schemas import SessionUser
from app.chat import service
from app.chat.deps import get_chat_http_client
from app.chat.schemas import AssistantRequest
from app.config import Settings, get_settings
from app.db import get_pool

router = APIRouter(tags=["chat"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
CurrentUser = Annotated[SessionUser, Depends(current_user)]
ChatHttpClient = Annotated[httpx.AsyncClient, Depends(get_chat_http_client)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/chat")
async def chat(
    data: AssistantRequest,
    pool: Pool,
    user: CurrentUser,
    client: ChatHttpClient,
    settings: Config,
) -> AssistantTransportResponse:
    async def run(controller: RunController) -> None:
        await service.run_callback(controller, data, user, pool, client, settings)

    return AssistantTransportResponse(create_run(run, state=data.state))

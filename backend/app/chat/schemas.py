"""Request models for the AssistantTransport wire contract.

Mirrors the shapes ``@assistant-ui/react``'s ``useAssistantTransportRuntime``
sends (confirmed against the reference backend in the ``assistant-ui``
project). Only what the client sends is modeled here — the response is a
stream of state-diff operations emitted by ``assistant_stream``, not a
pydantic-typed body.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

MessageRole = Literal["user", "assistant"]


class MessagePart(BaseModel):
    type: str  # "text" | "tool-call"
    text: str | None = None


class ThreadMessage(BaseModel):
    role: MessageRole
    parts: list[MessagePart]


class AddMessageCommand(BaseModel):
    type: Literal["add-message"] = "add-message"
    message: ThreadMessage


class AddToolResultCommand(BaseModel):
    type: Literal["add-tool-result"] = "add-tool-result"
    toolCallId: str
    result: dict[str, Any]


Command = Annotated[AddMessageCommand | AddToolResultCommand, Field(discriminator="type")]


class AssistantRequest(BaseModel):
    commands: list[Command]
    system: str | None = None
    tools: dict[str, Any] | None = None
    state: dict[str, Any] | None = None

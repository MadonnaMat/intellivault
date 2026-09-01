"""Request/response models for the auth routes.

The WebAuthn ceremony *options* are returned as the raw spec JSON
(``dict[str, Any]``) produced by ``webauthn.options_to_json`` — the shape
``@simplewebauthn/browser`` consumes directly. The ceremony *responses* posted
back by the browser are likewise accepted as ``dict[str, Any]`` and handed
straight to ``py_webauthn`` for verification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

DisplayName = Field(min_length=1, max_length=100)


class SessionUser(BaseModel):
    """The authenticated user behind the current session."""

    id: UUID
    email: str
    display_name: str


class RegisterBeginRequest(BaseModel):
    email: EmailStr
    display_name: str = DisplayName


class LoginBeginRequest(BaseModel):
    # Reserved for a future non-discoverable flow; discoverable login ignores it.
    email: EmailStr | None = None


class UpdateAccountRequest(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class AddPasskeyFinishRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    credential: dict[str, Any]


class CredentialSummary(BaseModel):
    """One registered passkey, as shown on the account page."""

    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    transports: list[str]


# The browser's PublicKeyCredential, serialised to JSON. Kept opaque here.
CeremonyResponse = dict[str, Any]
# The ceremony options returned by a "begin" call.
CeremonyOptions = dict[str, Any]

"""Passwordless authentication: WebAuthn passkeys and server-side sessions."""

from __future__ import annotations

from app.auth.router import router as auth_router

__all__ = ["auth_router"]

"""One place for the flags on every auth cookie we set.

``iv_session`` (path ``/``) and ``iv_ceremony`` (path ``/auth``) differ only in
name, path and lifetime; Secure / SameSite / Domain / HttpOnly come from config
so a split-domain deployment can widen them without touching call sites.
"""

from __future__ import annotations

from fastapi import Response

from app.config import Settings


def set_cookie(
    response: Response,
    name: str,
    value: str,
    *,
    settings: Settings,
    max_age: int,
    path: str,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
    )


def clear_cookie(response: Response, name: str, *, settings: Settings, path: str) -> None:
    response.delete_cookie(
        name,
        path=path,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
    )

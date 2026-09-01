"""Adapters between the WebAuthn JSON our API speaks and ``soft_webauthn``.

``soft_webauthn.SoftWebauthnDevice`` works with the raw ``navigator.credentials``
structures (bytes, not base64url), so tests translate the "begin" options into
that shape and translate the device's output back into the RegistrationResponse /
AuthenticationResponse JSON the "finish" endpoints expect.
"""

from __future__ import annotations

from typing import Any

from webauthn.helpers import base64url_to_bytes, bytes_to_base64url


def options_to_soft(options: dict[str, Any]) -> dict[str, Any]:
    """A "begin" response (JSON) -> the dict SoftWebauthnDevice.create/get wants."""
    pk = dict(options)
    pk["challenge"] = base64url_to_bytes(pk["challenge"])
    if "user" in pk:
        pk["user"] = {**pk["user"], "id": base64url_to_bytes(pk["user"]["id"])}
    for key in ("excludeCredentials", "allowCredentials"):
        if pk.get(key):
            pk[key] = [{**c, "id": base64url_to_bytes(c["id"])} for c in pk[key]]
    return {"publicKey": pk}


def registration_to_json(credential: dict[str, Any]) -> dict[str, Any]:
    raw = credential["rawId"]
    response = credential["response"]
    return {
        "id": bytes_to_base64url(raw),
        "rawId": bytes_to_base64url(raw),
        "response": {
            "clientDataJSON": bytes_to_base64url(response["clientDataJSON"]),
            "attestationObject": bytes_to_base64url(response["attestationObject"]),
            "transports": ["internal"],
        },
        "type": credential["type"],
        "clientExtensionResults": {},
        "authenticatorAttachment": "platform",
    }


def authentication_to_json(credential: dict[str, Any]) -> dict[str, Any]:
    raw = credential["rawId"]
    response = credential["response"]
    out: dict[str, Any] = {
        "id": bytes_to_base64url(raw),
        "rawId": bytes_to_base64url(raw),
        "response": {
            "clientDataJSON": bytes_to_base64url(response["clientDataJSON"]),
            "authenticatorData": bytes_to_base64url(response["authenticatorData"]),
            "signature": bytes_to_base64url(response["signature"]),
        },
        "type": credential["type"],
        "clientExtensionResults": {},
    }
    if response.get("userHandle") is not None:
        out["response"]["userHandle"] = bytes_to_base64url(response["userHandle"])
    return out

"""Fetch + text-extract source pages for the agent, with an SSRF guard.

Every URL — and every redirect hop — is resolved and checked against private /
loopback / link-local / reserved address space before we connect, so a crafted
search result can't turn the worker into a probe of postgres / neo4j / redis /
ollama. This module deliberately imports nothing from langgraph / langchain.

Known gap (documented, follow-up): httpx re-resolves the host when it connects,
so a DNS-rebinding race remains. Closing it means connecting to the validated IP
literal with an explicit ``sni_hostname`` / ``Host`` header.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel

from app.config import Settings

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_SKIP_TAGS = frozenset({"script", "style", "head", "noscript", "template"})

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class FetchedDoc(BaseModel):
    """One fetched source: the URL asked for and the extracted, truncated text."""

    url: str
    text: str


class SsrfError(ValueError):
    """A URL was rejected before connecting (bad scheme, or a non-public address)."""


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    """The worker's outbound client for source fetches — redirects handled by us."""
    return httpx.AsyncClient(
        follow_redirects=False,
        timeout=settings.agent_fetch_timeout,
        limits=httpx.Limits(max_connections=10),
        headers={"user-agent": "IntelliVault-Agent/0.1"},
    )


async def _resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(sockaddr[0]) for *_head, sockaddr in infos]


def _ip_is_public(ip: _IPAddress) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # 169.254.0.0/16 — incl. the 169.254.169.254 metadata IP
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def guard_url(url: str) -> str:
    """Return ``url`` unchanged, or raise SsrfError. http(s) + public IPs only."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in _ALLOWED_SCHEMES or not host:
        raise SsrfError(f"blocked scheme or missing host: {url!r}")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:  # non-numeric port in the authority
        raise SsrfError(f"invalid port in {url!r}") from exc
    addresses = await _resolve(host, port)
    if not addresses:
        raise SsrfError(f"no DNS answer for {host!r}")
    for address in addresses:
        if not _ip_is_public(ipaddress.ip_address(address)):
            raise SsrfError(f"{host} resolves to non-public {address}")
    return url


class _TextExtractor(HTMLParser):
    """Collect visible text, dropping <script>/<style>/<head>/… subtrees."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._chunks.append(data.strip())

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._chunks).split())


def _extract_text(body: bytes) -> str:
    parser = _TextExtractor()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser.text


async def _read_capped(response: httpx.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        total += len(chunk)
        if total >= limit:
            break
    return b"".join(chunks)[:limit]


async def fetch_text(client: httpx.AsyncClient, url: str, settings: Settings) -> FetchedDoc:
    """GET ``url``, following redirects ourselves, re-guarding every hop."""
    current = await guard_url(url)
    for _hop in range(settings.agent_fetch_max_redirects + 1):
        async with client.stream("GET", current, timeout=settings.agent_fetch_timeout) as response:
            location = response.headers.get("location") if response.is_redirect else None
            if location:
                current = await guard_url(urljoin(current, location))
                continue
            # A 3xx without a usable Location (or any 4xx/5xx) raises here —
            # raise_for_status() treats an unfollowed redirect as an error too.
            response.raise_for_status()
            body = await _read_capped(response, settings.agent_fetch_max_bytes)
        return FetchedDoc(url=url, text=_extract_text(body)[: settings.agent_source_char_limit])
    raise SsrfError(f"too many redirects for {url!r}")

"""app.agent.fetch — the SSRF guard, redirect handling, text extraction."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.agent import fetch
from app.agent.fetch import SsrfError, _extract_text, fetch_text, guard_url
from app.config import Settings

# Captured before any fixture patches fetch._resolve.
_REAL_RESOLVE = fetch._resolve

_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    AGENT_SOURCE_CHAR_LIMIT="40",
    AGENT_FETCH_MAX_BYTES="64",
    AGENT_FETCH_MAX_REDIRECTS="2",
)

# host -> the addresses DNS "returns" for it
_DNS: dict[str, list[str]] = {
    "example.com": ["93.184.216.34"],
    "public.test": ["93.184.216.34"],
    "localhost.test": ["127.0.0.1"],
    "rfc1918.test": ["10.1.2.3"],
    "lan.test": ["192.168.1.1"],
    "metadata.test": ["169.254.169.254"],
    "v6-loopback.test": ["::1"],
    "v6-ula.test": ["fc00::1"],
    "v4mapped.test": ["::ffff:127.0.0.1"],
    "empty.test": [],
}


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(host: str, _port: int) -> list[str]:
        return _DNS.get(host, ["93.184.216.34"])

    monkeypatch.setattr(fetch, "_resolve", _resolve)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http:///nohost"])
async def test_guard_url_rejects_bad_scheme_or_host(url: str) -> None:
    with pytest.raises(SsrfError):
        await guard_url(url)


async def test_guard_url_rejects_a_non_numeric_port() -> None:
    with pytest.raises(SsrfError):
        await guard_url("http://example.com:notaport/")


@pytest.mark.parametrize(
    "host",
    [
        "localhost.test",
        "rfc1918.test",
        "lan.test",
        "metadata.test",
        "v6-loopback.test",
        "v6-ula.test",
        "v4mapped.test",
    ],
)
async def test_guard_url_rejects_non_public_addresses(host: str) -> None:
    with pytest.raises(SsrfError):
        await guard_url(f"http://{host}/page")


async def test_guard_url_rejects_when_dns_is_empty() -> None:
    with pytest.raises(SsrfError):
        await guard_url("http://empty.test/")


async def test_guard_url_wraps_a_resolution_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    async def _boom(_host: str, _port: int) -> list[str]:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(fetch, "_resolve", _boom)
    with pytest.raises(SsrfError, match="cannot resolve"):
        await guard_url("https://nope.invalid/x")


async def test_guard_url_allows_a_public_address() -> None:
    assert await guard_url("https://example.com/a") == "https://example.com/a"


def test_extract_text_drops_script_style_and_collapses_whitespace() -> None:
    html = """
    <html><head><title>t</title><style>.x{color:red}</style></head>
    <body><p>Hello   world</p><script>alert(1)</script><p>again</p></body></html>
    """
    assert _extract_text(html.encode()) == "Hello world again"


@respx.mock
async def test_fetch_text_extracts_and_truncates() -> None:
    respx.get("https://example.com/doc").mock(
        return_value=httpx.Response(200, html="<p>" + "word " * 50 + "</p>")
    )
    async with httpx.AsyncClient(follow_redirects=False) as client:
        doc = await fetch_text(client, "https://example.com/doc", _SETTINGS)

    assert doc.url == "https://example.com/doc"
    assert len(doc.text) == 40  # AGENT_SOURCE_CHAR_LIMIT


@respx.mock
async def test_fetch_text_follows_a_redirect_to_a_public_host() -> None:
    respx.get("https://example.com/start").mock(
        return_value=httpx.Response(302, headers={"location": "https://public.test/end"})
    )
    respx.get("https://public.test/end").mock(return_value=httpx.Response(200, html="<p>ok</p>"))
    async with httpx.AsyncClient(follow_redirects=False) as client:
        doc = await fetch_text(client, "https://example.com/start", _SETTINGS)
    assert doc.text == "ok"


@respx.mock
async def test_fetch_text_rejects_a_redirect_to_a_private_host() -> None:
    respx.get("https://example.com/eviltrap").mock(
        return_value=httpx.Response(302, headers={"location": "http://metadata.test/latest"})
    )
    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(SsrfError):
            await fetch_text(client, "https://example.com/eviltrap", _SETTINGS)


@respx.mock
async def test_fetch_text_gives_up_after_too_many_redirects() -> None:
    respx.get("https://example.com/loop").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.com/loop"})
    )
    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(SsrfError, match="too many redirects"):
            await fetch_text(client, "https://example.com/loop", _SETTINGS)


@respx.mock
async def test_fetch_text_caps_an_oversize_body() -> None:
    huge = "<p>" + "x" * 10_000 + "</p>"
    respx.get("https://example.com/big").mock(return_value=httpx.Response(200, html=huge))
    async with httpx.AsyncClient(follow_redirects=False) as client:
        doc = await fetch_text(client, "https://example.com/big", _SETTINGS)
    # body capped at 64 bytes, then text truncated to 40 chars
    assert len(doc.text) <= 40


@respx.mock
async def test_fetch_text_rejects_a_redirect_without_a_location() -> None:
    respx.get("https://example.com/bad-redirect").mock(return_value=httpx.Response(302))
    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_text(client, "https://example.com/bad-redirect", _SETTINGS)


async def test_resolve_hits_real_dns_for_localhost() -> None:
    # The one place the real getaddrinfo path is exercised (no network needed).
    addresses = await _REAL_RESOLVE("localhost", 80)
    assert any(a in {"127.0.0.1", "::1"} for a in addresses)


@respx.mock
async def test_fetch_text_raises_on_http_error() -> None:
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient(follow_redirects=False) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_text(client, "https://example.com/missing", _SETTINGS)


def test_build_http_client_does_not_auto_follow_redirects() -> None:
    client = fetch.build_http_client(_SETTINGS)
    assert client.follow_redirects is False


def test_build_http_client_sends_a_descriptive_user_agent() -> None:
    client = fetch.build_http_client(_SETTINGS)
    assert "github.com" in client.headers["user-agent"]  # descriptive UA with a contact URL

"""app.streaming — the SSE encoding helpers for hand-rolled stream endpoints."""

from __future__ import annotations

from app.streaming import format_sse, format_sse_comment


def test_format_sse_encodes_event_and_json_data() -> None:
    assert format_sse("status", {"a": 1}) == b'event: status\ndata: {"a": 1}\n\n'


def test_format_sse_comment_encodes_a_comment_line() -> None:
    assert format_sse_comment("keep-alive") == b": keep-alive\n\n"

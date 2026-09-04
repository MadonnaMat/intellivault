"""SSE encoding for hand-rolled streaming endpoints (agent run status).

Chat (``app/chat/``) speaks assistant-ui's AssistantTransport protocol via the
``assistant_stream`` package instead — this is for the one other streaming
endpoint, which just pushes plain named events.
"""

from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def format_sse_comment(text: str) -> bytes:
    return f": {text}\n\n".encode()

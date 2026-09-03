"""The FastAPI gateway must not import langgraph / langchain at import time.

The agent package is import-cheap on the gateway path (only the router);
langgraph + the LLM clients are pulled in lazily by the worker (via
``service.enqueue_run`` -> ``app.agent.tasks``).
"""

from __future__ import annotations

import subprocess
import sys

_HEAVY = ["langgraph", "langchain_ollama", "langchain_mcp_adapters"]


def test_importing_the_gateway_does_not_load_langgraph() -> None:
    code = (
        "import sys, app.main; "
        f"bad = [m for m in {_HEAVY!r} if m in sys.modules]; "
        "print(bad); "
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"gateway import pulled in: {result.stdout.strip()}"

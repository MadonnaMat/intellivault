"""The FastAPI gateway must not load langgraph / langchain.

The agent package is import-cheap on the gateway path: the router, and the
``service.enqueue_run`` -> ``import app.agent.tasks`` -> ``run_agent.kiq`` chain.
langgraph + the LLM clients are pulled in only when a task body actually runs,
i.e. in the worker process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HEAVY = ["langgraph", "langchain_ollama", "langchain_mcp_adapters"]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# What the gateway actually imports: the app itself, and the enqueue seam.
_GATEWAY_IMPORTS = ["app.main", "app.agent.tasks", "app.agent.broker"]


@pytest.mark.parametrize("module", _GATEWAY_IMPORTS)
def test_gateway_import_path_stays_langgraph_free(module: str) -> None:
    code = (
        f"import sys, importlib; importlib.import_module({module!r}); "
        f"bad = [m for m in {_HEAVY!r} if m in sys.modules]; "
        "print(bad); "
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=_BACKEND_ROOT,  # so `import app` resolves regardless of pytest's cwd
    )
    assert result.returncode == 0, (
        f"importing {module} pulled in {result.stdout.strip()} / {result.stderr.strip()}"
    )

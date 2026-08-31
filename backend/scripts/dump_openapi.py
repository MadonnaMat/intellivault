"""Write the gateway's OpenAPI schema to a file.

Run via `make openapi` (from the repo root). The committed schema at
repo-root `openapi.json` is the contract the frontend generates its types
from, so regenerate and commit it whenever a request/response model changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[2] / "openapi.json"

# The schema doesn't depend on real infrastructure — build the app with
# placeholder settings and tracing off so `make openapi` needs nothing running.
_SCHEMA_SETTINGS = Settings(
    _env_file=None,
    neo4j_password="placeholder",
    database_url="postgresql://user:pw@localhost:5432/intellivault",
    tracing_enabled=False,
)


def main() -> None:
    schema = create_app(_SCHEMA_SETTINGS).openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT}", file=sys.stderr)


if __name__ == "__main__":
    main()

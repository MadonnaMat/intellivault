"""Apply / roll back / list the Neo4j graph migrations.

Run from the repo root:

    make graph-migrate           # apply pending
    make graph-migrate-down      # roll everything back
    make graph-migrate-status    # show applied (A) / unapplied (U)

or ``docker compose run --rm graph-migrate``. Applying graph schema is a
deliberate step — nothing runs it automatically, the same as ``make migrate``
for Postgres.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from neo4j import AsyncGraphDatabase

from app.graph.migrations import (
    apply_graph_migrations,
    graph_migration_status,
    rollback_graph_migrations,
)

# Read Neo4j connection details straight from the environment rather than the
# full app Settings — this runner has no business requiring DATABASE_URL. The
# repo .env feeds native `make graph-migrate`; compose injects them directly.
# NEO4J_PASSWORD is a required secret — no default (see CLAUDE.md).
_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
_USER = os.environ.get("NEO4J_USER", "neo4j")


async def _run(command: str) -> None:
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("NEO4J_PASSWORD is required")
    # Migrations legitimately reference labels/properties that don't exist yet
    # (the _GraphMigration bookkeeping node on a first run), so silence the
    # server's "label does not exist" notifications for this connection.
    driver = AsyncGraphDatabase.driver(
        _URI, auth=(_USER, password), notifications_min_severity="OFF"
    )
    try:
        if command == "apply":
            ids = await apply_graph_migrations(driver)
            print("applied: " + (", ".join(ids) or "(nothing pending)"), file=sys.stderr)
        elif command == "rollback":
            ids = await rollback_graph_migrations(driver)
            print("rolled back: " + (", ".join(ids) or "(nothing applied)"), file=sys.stderr)
        else:
            for migration_id, applied in await graph_migration_status(driver):
                print(f"{'A' if applied else 'U'} {migration_id}", file=sys.stderr)
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", default="apply", choices=("apply", "rollback", "status")
    )
    asyncio.run(_run(parser.parse_args().command))


if __name__ == "__main__":
    main()

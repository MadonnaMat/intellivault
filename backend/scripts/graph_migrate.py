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
import sys

from neo4j import AsyncGraphDatabase

from app.config import get_settings
from app.graph.migrations import (
    apply_graph_migrations,
    graph_migration_status,
    rollback_graph_migrations,
)


async def _run(command: str) -> None:
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
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

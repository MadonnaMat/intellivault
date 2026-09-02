"""Guardrail: any Cypher that reads Entity nodes must scope by owner + visibility.

Neo4j Community has no row/property security — the only thing standing between
one tenant's private nodes and another is the ``WHERE`` clause in these files.
A new query file that ``MATCH``es ``:Entity`` without both ``owner_id`` and
``visibility`` fails this test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CYPHER_DIR = Path(__file__).resolve().parents[2] / "app" / "graph" / "cypher"


def _entity_reading_files() -> list[Path]:
    return [
        path
        for path in sorted(CYPHER_DIR.glob("*.cypher"))
        if "MATCH" in (text := path.read_text(encoding="utf-8")) and ":Entity" in text
    ]


@pytest.mark.parametrize("path", _entity_reading_files(), ids=lambda p: p.name)
def test_entity_reads_are_owner_and_visibility_scoped(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "owner_id" in text, f"{path.name}: reads :Entity without owner_id scoping"
    assert "visibility" in text, f"{path.name}: reads :Entity without visibility scoping"
    assert "// SECURITY:" in text, f"{path.name}: missing a // SECURITY: rationale comment"

"""Guardrail: the tenant-security rules that live only in Cypher.

Neo4j Community has no row/property security — the `WHERE` / node-pattern
predicates in `app/graph/cypher/` are the *entire* boundary between one tenant's
private data and another. This test fails a new query file that drops a rule.

Checks run against the **comment-stripped** body, so a rule mentioned only in a
`//` comment does not count.

  1. Any `.cypher` that MATCHes `:Entity` — or reads it out of a vector index via
     `db.index.vector.queryNodes` — must bind `owner_id` to `$owner_id` (in a
     node pattern or a WHERE), and carry a `// SECURITY:` rationale.
  2. The tenant-visible *reads* (`list_*` / `get_*` / `search_*`) must additionally
     contain the exact visibility predicate —
     `visibility = 'public' OR ... owner_id = $owner_id`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CYPHER_DIR = Path(__file__).resolve().parents[2] / "app" / "graph" / "cypher"

# owner_id compared to $owner_id in any form: `owner_id: $owner_id` (pattern),
# `owner_id = $owner_id`, `owner_id <> $owner_id`, `owner_id IN [...]`, etc.
_OWNER_SCOPED = re.compile(r"owner_id\s*(?::|=|<>|!=|\bIN\b|\bin\b)\s*\$owner_id")


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def _reads_entities(text: str) -> bool:
    return ":Entity" in text and ("MATCH" in text or "db.index.vector.queryNodes" in text)


def _entity_files() -> list[Path]:
    return [
        path
        for path in sorted(CYPHER_DIR.glob("*.cypher"))
        if _reads_entities(path.read_text(encoding="utf-8"))
    ]


@pytest.mark.parametrize("path", _entity_files(), ids=lambda p: p.name)
def test_entity_queries_are_owner_scoped(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    code = _strip_comments(raw)

    assert _OWNER_SCOPED.search(code), (
        f"{path.name}: MATCHes :Entity but never scopes owner_id against $owner_id"
    )
    assert "// SECURITY:" in raw, f"{path.name}: missing a // SECURITY: rationale comment"


@pytest.mark.parametrize(
    "path",
    [p for p in _entity_files() if p.name.startswith(("list_", "get_", "search_"))],
    ids=lambda p: p.name,
)
def test_visible_reads_carry_the_full_predicate(path: Path) -> None:
    code = _strip_comments(path.read_text(encoding="utf-8")).replace(" ", "")
    assert "visibility='public'OR" in code, (
        f"{path.name}: a tenant-visible read without the `visibility = 'public' OR …` predicate"
    )
    assert "owner_id=$owner_id" in code, f"{path.name}: read predicate does not check owner_id"

"""Each LangGraph node in isolation, driven by hand-rolled fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from app.agent import fetch, nodes
from app.agent.graph_state import initial_state
from app.agent.schemas import DigestEntity, GraphDigest, Plan, SearchHit, StructuredResult
from app.config import Settings
from tests.agent.conftest import FakeChatModel, FakePool, FakeSearchTool, fake_deps
from tests.graph.conftest import FakeNeo4jDriver

_OWNER = str(uuid4())
_SETTINGS_WITH_CAP = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    AGENT_SURVEY_MAX_ENTITIES="1",
)


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(host: str, _port: int) -> list[str]:
        return ["10.0.0.1"] if host == "private.test" else ["93.184.216.34"]

    monkeypatch.setattr(fetch, "_resolve", _resolve)


def _state(**over: Any) -> Any:
    base = initial_state("history of the transistor", _OWNER, str(uuid4()))
    base.update(over)  # type: ignore[typeddict-item]
    return base


def _node_row(name: str, kind: str = "org") -> dict[str, Any]:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return {
        "e": {
            "id": str(uuid4()),
            "owner_id": _OWNER,
            "visibility": "private",
            "name": name,
            "kind": kind,
            "attributes": "{}",
            "created_at": now,
            "updated_at": now,
        }
    }


def _edge_row() -> dict[str, Any]:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return {
        "r": {
            "id": str(uuid4()),
            "owner_id": _OWNER,
            "kind": "employs",
            "visibility": "private",
            "created_at": now,
            "updated_at": now,
        },
        "from_id": str(uuid4()),
        "to_id": str(uuid4()),
    }


async def test_plan_node_produces_a_plan() -> None:
    chat = FakeChatModel(structured={"Plan": [{"summary": "look into it", "queries": ["a", "b"]}]})
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    out = await nodes.plan_node(_state(), deps=deps)
    assert out["plan"] == Plan(summary="look into it", queries=["a", "b"])


async def test_survey_graph_node_scopes_by_owner_and_builds_a_digest() -> None:
    driver = FakeNeo4jDriver([_node_row("Bell Labs")], [])
    deps = fake_deps(driver=driver)
    out = await nodes.survey_graph_node(_state(), deps=deps)

    digest = out["existing_graph"]
    assert isinstance(digest, GraphDigest)
    assert [e.name for e in digest.entities] == ["Bell Labs"]
    assert all(params["owner_id"] == _OWNER for _q, params in driver.calls)
    assert out["skipped"] == []  # nothing truncated


async def test_survey_graph_node_caps_and_ranks_by_topic_relevance() -> None:
    entities = [
        _node_row("Unrelated Widget"),
        _node_row("Transistor History"),
        _node_row("Also Off"),
    ]
    edge = _edge_row()
    edge["from_id"] = entities[1]["e"]["id"]  # points at the kept entity
    edge["to_id"] = entities[0]["e"]["id"]  # ...and one that gets dropped
    driver = FakeNeo4jDriver(entities, [edge])
    settings = _SETTINGS_WITH_CAP
    deps = fake_deps(driver=driver, settings=settings)

    out = await nodes.survey_graph_node(
        _state(plan=Plan(summary="s", queries=["transistor invention"])), deps=deps
    )
    digest = out["existing_graph"]
    assert [e.name for e in digest.entities] == ["Transistor History"]  # topic match wins
    assert digest.relationships == []  # the edge's other endpoint was dropped
    assert out["skipped"] == ["survey: showing 1 of 3 visible entities"]


async def test_search_node_dedupes_caps_and_drops_ssrf_urls() -> None:
    results = [
        {"url": "https://a.test/1", "title": "A"},
        {"url": "https://a.test/1", "title": "dup"},
        {"url": "https://private.test/x", "title": "internal"},
        {"url": "https://b.test/2"},
        {"url": "https://c.test/3"},
        {"url": "https://d.test/4"},  # past AGENT_MAX_SOURCES=3
    ]
    tool = FakeSearchTool(results)
    deps = fake_deps(driver=FakeNeo4jDriver(), search_tool=tool)
    out = await nodes.search_node(_state(plan=Plan(summary="s", queries=["q"])), deps=deps)

    assert [h.url for h in out["search_hits"]] == [
        "https://a.test/1",
        "https://b.test/2",
        "https://c.test/3",
    ]
    assert any("private.test" in note for note in out["skipped"])


async def test_search_node_no_plan_is_a_noop() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver())
    out = await nodes.search_node(_state(plan=None), deps=deps)
    assert out["search_hits"] == []


@respx.mock
async def test_fetch_node_tolerates_a_per_url_failure() -> None:
    respx.get("https://ok.test/a").mock(return_value=httpx.Response(200, html="<p>hello</p>"))
    respx.get("https://bad.test/b").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(follow_redirects=False) as client:
        deps = fake_deps(driver=FakeNeo4jDriver(), http_client=client)
        out = await nodes.fetch_node(
            _state(
                search_hits=[
                    SearchHit(url="https://ok.test/a"),
                    SearchHit(url="https://bad.test/b"),
                ]
            ),
            deps=deps,
        )
    assert [d.text for d in out["documents"]] == ["hello"]
    assert any("bad.test" in note for note in out["skipped"])


async def test_analyze_node_returns_model_text() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=FakeChatModel(text="the notes"))
    out = await nodes.analyze_node(_state(), deps=deps)
    assert out["analysis"] == "the notes"


async def test_structure_node_validates_and_dedupes_against_the_graph() -> None:
    existing_id = uuid4()
    digest = GraphDigest(entities=[DigestEntity(id=existing_id, name="Bell Labs", kind="org")])
    chat = FakeChatModel(
        structured={
            "StructuredResult": [
                {
                    "entities": [
                        {"temp_id": "e1", "name": "Bell Labs", "kind": "org"},
                        {"temp_id": "e2", "name": "William Shockley", "kind": "person"},
                    ],
                    "relationships": [{"from_ref": "e2", "to_ref": "e1", "kind": "worked_at"}],
                }
            ]
        }
    )
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    out = await nodes.structure_node(_state(existing_graph=digest), deps=deps)

    result = out["structured"]
    assert result.entities[0].existing_id == existing_id  # deduped
    assert result.entities[1].existing_id is None


async def test_structure_node_survives_unparseable_output() -> None:
    chat = FakeChatModel(structured={"StructuredResult": [{"entities": [{"name": 5}]}]})
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    out = await nodes.structure_node(_state(), deps=deps)
    assert out["structured"] == StructuredResult()
    assert any(note.startswith("structure:") for note in out["skipped"])


async def test_commit_node_creates_private_nodes_and_records_progress() -> None:
    existing_id = uuid4()
    structured = StructuredResult.model_validate(
        {
            "entities": [
                {"temp_id": "e1", "name": "New Co", "kind": "org"},
                {"temp_id": "e2", "name": "Known", "kind": "org", "existing_id": str(existing_id)},
            ],
            "relationships": [
                {"from_ref": "e2", "to_ref": "e1", "kind": "spun_off"},
                {"from_ref": "e1", "to_ref": "ghost", "kind": "broken"},
            ],
        }
    )
    # create_entity -> one row; create_relationship -> one row
    driver = FakeNeo4jDriver([_node_row("New Co")], [_edge_row()])
    pool = FakePool()
    deps = fake_deps(driver=driver, pool=pool)
    out = await nodes.commit_node(_state(structured=structured), deps=deps)

    assert len(out["committed_entity_ids"]) == 1  # e2 was a link, not a create
    assert len(out["committed_relationship_ids"]) == 1
    assert any("ghost" in note for note in out["skipped"])
    create_entity_call = next(q for q, _ in driver.calls if "CREATE (e:Entity" in q)
    assert "$visibility" in create_entity_call
    assert [p for _q, p in driver.calls if "CREATE (e:Entity" in _q][0]["visibility"] == "private"
    assert any("array_append(committed_entity_ids" in q for q, _ in pool.calls)


@pytest.mark.parametrize(
    ("raw", "expected_urls"),
    [
        ('[{"url": "https://a.test"}]', ["https://a.test"]),
        ({"results": [{"link": "https://b.test"}]}, ["https://b.test"]),
        ("not json", []),
        (12345, []),
        (["plain string", {"title": "no url"}], []),
    ],
)
def test_parse_search_result_normalises_shapes(raw: Any, expected_urls: list[str]) -> None:
    assert [h.url for h in nodes._parse_search_result(raw)] == expected_urls


def test_text_flattens_list_and_non_string_content() -> None:
    assert nodes._text(["a", "b"]) == "a b"
    assert nodes._text(42) == "42"
    assert nodes._text("plain") == "plain"


async def test_commit_node_routes_a_rejected_edge_into_skipped() -> None:
    structured = StructuredResult.model_validate(
        {
            "entities": [{"temp_id": "e1", "name": "A", "kind": "org"}],
            "relationships": [{"from_ref": "e1", "to_ref": "e1", "kind": "self"}],
        }
    )
    # create_entity ok; create_relationship -> [] then relationship_endpoints -> [] => 404
    driver = FakeNeo4jDriver([_node_row("A")], [], [])
    deps = fake_deps(driver=driver, pool=FakePool())
    out = await nodes.commit_node(_state(structured=structured), deps=deps)

    assert out["committed_relationship_ids"] == []
    assert any("e1->e1" in note for note in out["skipped"])

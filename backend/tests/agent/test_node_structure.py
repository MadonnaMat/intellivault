"""app.agent.nodes.structure"""

from __future__ import annotations

from uuid import uuid4

from app.agent.fetch import FetchedDoc
from app.agent.nodes import critique_node, structure_node
from app.agent.schemas import DigestEntity, GraphDigest, StructuredResult
from tests.agent.conftest import FakeChatModel, fake_deps, make_state
from tests.graph.conftest import FakeNeo4jDriver


async def test_validates_and_dedupes_against_the_graph() -> None:
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
    out = await structure_node(
        make_state(existing_graph=digest), deps=fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    )
    result = out["structured"]
    assert result.entities[0].existing_id == existing_id
    assert result.entities[1].existing_id is None


async def test_survives_unparseable_output() -> None:
    chat = FakeChatModel(structured={"StructuredResult": [{"entities": [{"name": 5}]}]})
    out = await structure_node(
        make_state(), deps=fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    )
    assert out["structured"] == StructuredResult()
    assert any(note.startswith("structure:") for note in out["skipped"])


_DRAFT = {
    "entities": [{"temp_id": "e1", "name": "Bell Labs", "kind": "org"}],
    "relationships": [],
}


async def test_critique_ok_clears_the_critique() -> None:
    chat = FakeChatModel(structured={"Critique": [{"verdict": "ok"}]})
    out = await critique_node(
        make_state(
            structured=StructuredResult.model_validate(_DRAFT),
            documents=[FetchedDoc(url="https://s/1", text="Bell Labs")],
        ),
        deps=fake_deps(driver=FakeNeo4jDriver(), chat_model=chat),
    )
    assert out["critique"] is None
    assert out["critique_attempts"] == 1


async def test_critique_revise_records_notes_for_the_retry() -> None:
    payload = {"verdict": "revise", "notes": "invented an entity"}
    chat = FakeChatModel(structured={"Critique": [payload]})
    out = await critique_node(
        make_state(structured=StructuredResult.model_validate(_DRAFT), documents=[]),
        deps=fake_deps(driver=FakeNeo4jDriver(), chat_model=chat),
    )
    assert out["critique"] == "invented an entity"
    assert any("invented an entity" in n for n in out["skipped"])


async def test_critique_skips_an_empty_draft() -> None:
    out = await critique_node(
        make_state(structured=StructuredResult()), deps=fake_deps(driver=FakeNeo4jDriver())
    )
    assert out["critique"] is None

"""app.agent.llm — build_chat_model wiring + the structured() retry helper."""

from __future__ import annotations

from typing import Any, cast

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_ollama import ChatOllama

from app.agent.llm import StructuredOutputError, build_chat_model, structured
from app.agent.schemas import Plan
from app.config import Settings

_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    OLLAMA_URL="http://ollama.test:11434",
    OLLAMA_CHAT_MODEL="qwen3:8b",
    AGENT_LLM_TEMPERATURE="0.0",
)

_GOOD = {"summary": "s", "queries": ["a", "b"]}
_BAD = {"summary": "s"}  # missing queries


class _FakeRunnable:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.prompts: list[list[BaseMessage]] = []

    async def ainvoke(self, prompt: list[BaseMessage]) -> Any:
        self.prompts.append(prompt)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeChatModel:
    def __init__(self, responses: list[Any]) -> None:
        self.runnable = _FakeRunnable(responses)

    def with_structured_output(self, _schema: Any, **_kw: Any) -> _FakeRunnable:
        return self.runnable


def _model(responses: list[Any]) -> tuple[BaseChatModel, _FakeRunnable]:
    fake = _FakeChatModel(responses)
    return cast(BaseChatModel, fake), fake.runnable


def test_build_chat_model_wires_settings() -> None:
    model = build_chat_model(_SETTINGS)
    assert isinstance(model, ChatOllama)
    assert model.model == "qwen3:8b"
    assert model.base_url == "http://ollama.test:11434"
    assert model.temperature == 0.0


async def test_structured_returns_a_validated_instance() -> None:
    model, runnable = _model([_GOOD])
    result = await structured(model, Plan, [HumanMessage(content="plan it")])
    assert result == Plan(summary="s", queries=["a", "b"])
    assert len(runnable.prompts) == 1


async def test_structured_retries_once_then_succeeds() -> None:
    model, runnable = _model([_BAD, _GOOD])
    result = await structured(model, Plan, [HumanMessage(content="plan it")])
    assert result.queries == ["a", "b"]
    assert len(runnable.prompts) == 2
    # the retry prompt appends a corrective message
    assert isinstance(runnable.prompts[1][-1], HumanMessage)
    assert "schema" in str(runnable.prompts[1][-1].content)


async def test_structured_retries_on_an_ainvoke_exception() -> None:
    model, runnable = _model([ValueError("model exploded"), _GOOD])
    result = await structured(model, Plan, [HumanMessage(content="x")])
    assert result.summary == "s"
    assert len(runnable.prompts) == 2


async def test_structured_raises_after_exhausting_retries() -> None:
    model, _ = _model([_BAD, _BAD])
    with pytest.raises(StructuredOutputError):
        await structured(model, Plan, [HumanMessage(content="x")])


async def test_structured_honours_a_higher_retry_count() -> None:
    model, runnable = _model([_BAD, _BAD, _GOOD])
    result = await structured(model, Plan, [HumanMessage(content="x")], retries=2)
    assert result.queries == ["a", "b"]
    assert len(runnable.prompts) == 3

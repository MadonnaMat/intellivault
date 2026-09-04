"""The local Ollama chat model + a structured-output helper for the nodes.

``ChatOllama.with_structured_output`` on a small local model (qwen3:8b) is not
always reliable — this wraps it with a pydantic re-validation and one retry, and
the callers treat a final failure as "no output" rather than a run failure.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel

from app.config import Settings


class StructuredOutputError(RuntimeError):
    """The model never produced output matching the requested schema."""


def build_chat_model(settings: Settings) -> BaseChatModel:
    return ChatOllama(
        base_url=settings.ollama_url,
        model=settings.ollama_chat_model,
        temperature=settings.agent_llm_temperature,
        reasoning=settings.agent_llm_reasoning,
        # httpx timeout for the underlying ollama.AsyncClient — a model that
        # stops streaming must not hang the run.
        client_kwargs={"timeout": settings.agent_llm_timeout},
    )


async def structured[TModel: BaseModel](
    model: BaseChatModel,
    schema: type[TModel],
    messages: list[BaseMessage],
    *,
    retries: int = 1,
) -> TModel:
    """Invoke ``model`` for a ``schema`` instance, re-validating and retrying once."""
    runnable = model.with_structured_output(schema)
    prompt = list(messages)
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            raw = await runnable.ainvoke(prompt)
            return schema.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - any parse/validation failure retries
            last_error = exc
            prompt = [
                *messages,
                HumanMessage(
                    content=f"Your previous reply did not match the required schema ({exc}). "
                    "Reply again with only the valid structured object."
                ),
            ]
    raise StructuredOutputError(str(last_error))

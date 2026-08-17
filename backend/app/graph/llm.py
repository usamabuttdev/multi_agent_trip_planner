from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import get_settings

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add an OpenRouter key."
        )
    return ChatOpenAI(
        model=settings.openrouter_model,
        api_key=SecretStr(settings.openrouter_api_key),
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        default_headers={
            "HTTP-Referer": "http://localhost:5173",
            "X-Title": "Trip Orchestrator",
        },
    )


def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                text = getattr(block, "text", None)
                parts.append(text if isinstance(text, str) else "")
        return "".join(parts)
    if hasattr(content, "content"):
        return message_text(content.content)
    return str(content or "")


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _JSON_FENCE.sub("", (text or "").strip())
    try:
        loaded = json.loads(cleaned)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        loaded = json.loads(cleaned[start : end + 1])
        if isinstance(loaded, dict):
            return loaded
    raise ValueError(f"Model did not return JSON (got {cleaned[:180]!r})")


def structured_llm(schema: type[BaseModel], temperature: float = 0.3):
    return get_llm(temperature=temperature).with_structured_output(schema)


async def ainvoke_text(messages: list[BaseMessage], temperature: float = 0.2) -> str:
    response = await get_llm(temperature=temperature).ainvoke(messages)
    return message_text(response.content).strip()


async def ainvoke_structured(
    schema: type[BaseModel],
    messages: list[BaseMessage],
    *,
    temperature: float = 0.3,
    retries: int = 1,
) -> BaseModel:
    """Ask for JSON explicitly and parse it. OpenRouter free models often ignore tool/schema calls."""
    llm = get_llm(temperature=temperature)
    schema_prompt = (
        "Reply with a single JSON object only. No markdown, no preface, no safety labels. "
        "Match this schema:\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}"
    )
    payload: list[BaseMessage] = [*messages, HumanMessage(content=schema_prompt)]
    last_error: Exception | None = None

    try:
        native = await llm.with_structured_output(schema).ainvoke(messages)
        if isinstance(native, schema):
            return native
        if isinstance(native, dict):
            return schema.model_validate(native)
    except (ValidationError, ValueError, json.JSONDecodeError, TypeError) as exc:
        last_error = exc
    except Exception as exc:  # noqa: BLE001 — tool-calling often 400s on free models
        last_error = exc

    for _attempt in range(retries + 1):
        response = await llm.ainvoke(payload)
        text = message_text(response.content)
        try:
            return schema.model_validate(extract_json_object(text))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            payload = [
                *payload,
                AIMessage(content=text or ""),
                HumanMessage(
                    content=(
                        f"Invalid. Error: {exc}. "
                        "Output ONLY the JSON object for the schema. No other text."
                    )
                ),
            ]

    raise RuntimeError(str(last_error) if last_error else f"Could not parse {schema.__name__}")

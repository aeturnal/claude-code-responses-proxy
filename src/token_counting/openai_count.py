"""OpenAI-aligned token counting utilities."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

import tiktoken

from src.schema.openai import FunctionTool, InputMessageItem, InputTextItem

CHAT_FALLBACK_MODEL = "gpt-4o-mini-2024-07-18"
KNOWN_CHAT_MODELS = {
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-0613",
    "gpt-4-0613",
    "gpt-4-32k-0613",
    "gpt-4o",
    "gpt-4o-2024-08-06",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
}

TOOL_OVERHEAD_BY_MODEL = {
    "gpt-3.5-turbo-0125": 4,
    "gpt-3.5-turbo-0613": 4,
    "gpt-4-0613": 4,
    "gpt-4-32k-0613": 4,
    "gpt-4o": 4,
    "gpt-4o-2024-08-06": 4,
    "gpt-4o-mini": 4,
    "gpt-4o-mini-2024-07-18": 4,
}


def get_encoding(model: str) -> tiktoken.Encoding:
    """Return the OpenAI encoding for a model with fallback."""

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def _as_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    if isinstance(value, dict):
        return value
    return {}


def _normalize_message_item(message: Any) -> Dict[str, str]:
    if isinstance(message, InputMessageItem):
        role = message.role
        content_items = message.content
        name = None
    elif isinstance(message, dict):
        role = message.get("role")
        content_items = message.get("content", [])
        name = message.get("name")
    else:
        role = getattr(message, "role", None)
        content_items = getattr(message, "content", [])
        name = getattr(message, "name", None)

    texts: List[str] = []
    for item in content_items or []:
        if isinstance(item, InputTextItem):
            text = item.text
        elif isinstance(item, dict):
            text = item.get("text")
        else:
            text = getattr(item, "text", "")
        if text:
            texts.append(text)
    content = "\n".join(texts)
    normalized: Dict[str, str] = {"role": str(role), "content": content}
    if name:
        normalized["name"] = str(name)
    return normalized


def _normalize_messages(input_items: Iterable[Any]) -> List[Dict[str, str]]:
    return [_normalize_message_item(item) for item in input_items]


def count_message_tokens(messages: List[Dict[str, str]], model: str) -> int:
    """Count tokens for OpenAI-style messages using cookbook constants."""

    if model not in KNOWN_CHAT_MODELS:
        return count_message_tokens(messages, CHAT_FALLBACK_MODEL)

    encoding = get_encoding(model)
    tokens_per_message = 3
    tokens_per_name = 1
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            if value is None:
                continue
            num_tokens += len(encoding.encode(str(value)))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3
    return num_tokens


def _normalize_tool(tool: Any) -> Dict[str, Any]:
    if isinstance(tool, FunctionTool):
        tool_payload = _as_dict(tool)
    else:
        tool_payload = _as_dict(tool)

    if "function" in tool_payload:
        function_payload = _as_dict(tool_payload.get("function"))
        return function_payload

    return tool_payload


def count_tool_tokens(tools: Optional[Iterable[Any]], model: str) -> int:
    """Count tokens for tool definitions using OpenAI cookbook approach."""

    if not tools:
        return 0
    encoding = get_encoding(model)
    overhead = TOOL_OVERHEAD_BY_MODEL.get(
        model, TOOL_OVERHEAD_BY_MODEL[CHAT_FALLBACK_MODEL]
    )
    total_tokens = 0
    for tool in tools:
        function = _normalize_tool(tool)
        total_tokens += overhead
        name = function.get("name") or ""
        description = function.get("description") or ""
        parameters = function.get("parameters") or {}
        if name:
            total_tokens += len(encoding.encode(name))
        if description:
            total_tokens += len(encoding.encode(description))
        parameters_json = json.dumps(
            parameters, separators=(",", ":"), ensure_ascii=False
        )
        total_tokens += len(encoding.encode(parameters_json))
    return total_tokens


def count_openai_request_tokens(request: Any) -> int:
    """Count input tokens for an OpenAI Responses request."""

    payload = _as_dict(request)
    model = payload.get("model")
    if not model:
        raise ValueError("model is required for token counting")
    input_items = payload.get("input", [])
    messages = _normalize_messages(input_items)
    instructions = payload.get("instructions")
    if instructions:
        messages = [{"role": "system", "content": instructions}] + messages

    message_tokens = count_message_tokens(messages, model)
    tool_tokens = count_tool_tokens(payload.get("tools"), model)
    return int(message_tokens + tool_tokens)

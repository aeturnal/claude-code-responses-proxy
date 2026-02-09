"""Redaction and summary helpers for Anthropic message request/response shapes."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

from src.observability.redaction_shared import (
    LOG_ARRAY_LIMIT,
    normalize_payload,
    redact_text,
    redact_value,
    redaction_mode,
    truncate_list,
)
from src.schema.anthropic import MessagesRequest


def _redact_text_blocks(
    blocks: Iterable[Dict[str, Any]], mode: Optional[str], limit: int
) -> tuple[List[Dict[str, Any]], bool]:
    block_list = list(blocks)
    block_list, truncated = truncate_list(block_list, limit)
    redacted: List[Dict[str, Any]] = []
    for block in block_list:
        if not isinstance(block, dict):
            redacted.append(block)
            continue
        if block.get("type") == "text":
            updated = dict(block)
            updated["text"] = redact_text(block.get("text", ""), mode)
            redacted.append(updated)
            continue
        if block.get("type") == "tool_result":
            updated = dict(block)
            content = block.get("content")
            if isinstance(content, list):
                redacted_content, content_truncated = _redact_text_blocks(
                    content, mode, limit
                )
                updated["content"] = redacted_content
                truncated = truncated or content_truncated
            elif isinstance(content, str):
                updated["content"] = redact_text(content, mode)
            redacted.append(updated)
            continue
        if block.get("type") == "tool_use":
            updated = dict(block)
            if "input" in updated:
                updated["input"] = redact_value(updated.get("input"), mode)
            redacted.append(updated)
            continue
        redacted.append(block)
    return redacted, truncated


def summarize_messages_request(
    payload: Union[MessagesRequest, Dict[str, Any]],
) -> Dict[str, Any]:
    data = normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    messages = data.get("messages")
    tools = data.get("tools")
    message_count = len(messages) if isinstance(messages, list) else 0
    tool_definition_count = len(tools) if isinstance(tools, list) else 0
    tool_use_count = 0
    tool_result_count = 0
    tool_name_counts: Dict[str, int] = {}

    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use":
                    tool_use_count += 1
                    name = block.get("name")
                    if isinstance(name, str) and name:
                        tool_name_counts[name] = tool_name_counts.get(name, 0) + 1
                elif block_type == "tool_result":
                    tool_result_count += 1

    return {
        "message_count": message_count,
        "tool_definition_count": tool_definition_count,
        "tool_use_count": tool_use_count,
        "tool_result_count": tool_result_count,
        "tool_name_counts": tool_name_counts,
    }


def redact_messages_request(
    payload: Union[MessagesRequest, Dict[str, Any]],
) -> Dict[str, Any]:
    data = normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    mode = redaction_mode(None)
    if mode == "none":
        return data
    redacted = dict(data)
    truncated = False

    system = data.get("system")
    if isinstance(system, list):
        redacted_system, system_truncated = _redact_text_blocks(
            system, mode, LOG_ARRAY_LIMIT
        )
        redacted["system"] = redacted_system
        truncated = truncated or system_truncated
    elif system is not None:
        redacted["system"] = redact_text(system, mode)

    messages = data.get("messages")
    if isinstance(messages, list):
        messages, messages_truncated = truncate_list(messages, LOG_ARRAY_LIMIT)
        truncated = truncated or messages_truncated
        updated_messages = []
        for message in messages:
            if not isinstance(message, dict):
                updated_messages.append(message)
                continue
            updated = dict(message)
            content = message.get("content")
            if isinstance(content, list):
                redacted_content, content_truncated = _redact_text_blocks(
                    content, mode, LOG_ARRAY_LIMIT
                )
                updated["content"] = redacted_content
                truncated = truncated or content_truncated
            elif content is not None:
                updated["content"] = redact_text(content, mode)
            updated_messages.append(updated)
        redacted["messages"] = updated_messages

    tools = data.get("tools")
    if isinstance(tools, list):
        tools, tools_truncated = truncate_list(tools, LOG_ARRAY_LIMIT)
        truncated = truncated or tools_truncated
        updated_tools = []
        for tool in tools:
            if not isinstance(tool, dict):
                updated_tools.append(tool)
                continue
            updated = dict(tool)
            if "name" in updated:
                updated["name"] = redact_text(updated.get("name"), mode)
            if "description" in updated:
                updated["description"] = redact_text(updated.get("description"), mode)
            if "parameters" in updated:
                updated["parameters"] = redact_value(updated.get("parameters"), mode)
            if "input_schema" in updated:
                updated["input_schema"] = redact_value(updated.get("input_schema"), mode)
            updated_tools.append(updated)
        redacted["tools"] = updated_tools

    tool_choice = data.get("tool_choice")
    if isinstance(tool_choice, dict):
        updated_choice = dict(tool_choice)
        if "name" in updated_choice:
            updated_choice["name"] = redact_text(updated_choice.get("name"), mode)
        if "input" in updated_choice:
            updated_choice["input"] = redact_value(updated_choice.get("input"), mode)
        redacted["tool_choice"] = updated_choice

    if truncated:
        redacted["payload_truncated"] = True

    return redacted


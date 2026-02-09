"""Redaction helpers for generic payloads and OpenAI/Anthropic response envelopes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.observability.redaction_shared import (
    LOG_ARRAY_LIMIT,
    REDACTION_TOKEN,
    SENSITIVE_KEYS,
    normalize_key,
    normalize_payload,
    redact_text,
    redact_value,
    redaction_mode,
    truncate_list,
)


def _redact_generic_value(value: Any, mode: Optional[str]) -> tuple[Any, bool]:
    truncated = False
    if isinstance(value, str):
        return redact_text(value, mode), False
    if isinstance(value, list):
        items, list_truncated = truncate_list(value, LOG_ARRAY_LIMIT)
        truncated = truncated or list_truncated
        redacted_items = []
        for item in items:
            redacted_item, item_truncated = _redact_generic_value(item, mode)
            truncated = truncated or item_truncated
            redacted_items.append(redacted_item)
        return redacted_items, truncated
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = normalize_key(key)
            if normalized_key in SENSITIVE_KEYS:
                redacted[key] = REDACTION_TOKEN
                continue
            redacted_item, item_truncated = _redact_generic_value(item, mode)
            truncated = truncated or item_truncated
            redacted[key] = redacted_item
        return redacted, truncated
    return value, False


def redact_generic_payload(payload: Any) -> Any:
    mode = redaction_mode(None)
    if mode == "none":
        return normalize_payload(payload)
    redacted, truncated = _redact_generic_value(payload, mode)
    if truncated and isinstance(redacted, dict):
        redacted = dict(redacted)
        redacted["payload_truncated"] = True
    return redacted


def redact_anthropic_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    mode = redaction_mode(None)
    if mode == "none":
        return data
    redacted = dict(data)
    content = data.get("content")
    if isinstance(content, list):
        updated_content = []
        for block in content:
            if not isinstance(block, dict):
                updated_content.append(block)
                continue
            if block.get("type") == "text":
                updated = dict(block)
                updated["text"] = redact_text(block.get("text", ""), mode)
                updated_content.append(updated)
                continue
            if block.get("type") == "tool_use":
                updated = dict(block)
                if "input" in updated:
                    updated["input"] = redact_value(updated.get("input"), mode)
                updated_content.append(updated)
                continue
            updated_content.append(block)
        redacted["content"] = updated_content
    return redacted


def redact_openai_error(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    mode = redaction_mode(None)
    if mode == "none":
        return data
    redacted = dict(data)
    error = data.get("error")
    if isinstance(error, dict):
        updated_error = dict(error)
        if "message" in updated_error:
            updated_error["message"] = redact_text(updated_error.get("message"), mode)
        if "param" in updated_error:
            updated_error["param"] = redact_text(updated_error.get("param"), mode)
        redacted["error"] = updated_error
    return redacted


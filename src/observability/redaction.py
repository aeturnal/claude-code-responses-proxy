"""PII redaction helpers for observability payloads."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Union

from src.config import OBS_REDACTION_MODE
from src.schema.anthropic import MessagesRequest

REDACTION_TOKEN = "[REDACTED]"


@lru_cache(maxsize=1)
def _get_presidio_engines():
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise RuntimeError("Presidio not available") from exc
    return AnalyzerEngine(), AnonymizerEngine()


def _redaction_mode(override: Optional[str] = None) -> str:
    mode = (override or OBS_REDACTION_MODE or "full").strip().lower()
    if mode not in {"full", "partial"}:
        return "full"
    return mode


def redact_text(text: Any, mode: Optional[str] = None) -> Any:
    """Redact a string value, optionally with partial redaction."""

    if not isinstance(text, str):
        return text

    mode = _redaction_mode(mode)
    if mode == "full":
        return REDACTION_TOKEN

    try:
        analyzer, anonymizer = _get_presidio_engines()
        results = analyzer.analyze(text=text, language="en")
        if not results:
            return text
        from presidio_anonymizer.entities import OperatorConfig

        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": REDACTION_TOKEN})
            },
        )
        return anonymized.text
    except Exception:
        return REDACTION_TOKEN


def _normalize_payload(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if hasattr(payload, "dict"):
        return payload.dict(exclude_none=True)
    return payload


def _redact_value(value: Any, mode: Optional[str]) -> Any:
    if isinstance(value, str):
        return redact_text(value, mode)
    if isinstance(value, list):
        return [_redact_value(item, mode) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(val, mode) for key, val in value.items()}
    return value


def _redact_text_blocks(
    blocks: Iterable[Dict[str, Any]], mode: Optional[str]
) -> List[Dict[str, Any]]:
    redacted: List[Dict[str, Any]] = []
    for block in blocks:
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
                updated["content"] = _redact_text_blocks(content, mode)
            elif isinstance(content, str):
                updated["content"] = redact_text(content, mode)
            redacted.append(updated)
            continue
        if block.get("type") == "tool_use":
            updated = dict(block)
            if "input" in updated:
                updated["input"] = _redact_value(updated.get("input"), mode)
            redacted.append(updated)
            continue
        redacted.append(block)
    return redacted


def redact_messages_request(
    payload: Union[MessagesRequest, Dict[str, Any]],
) -> Dict[str, Any]:
    data = _normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    mode = _redaction_mode(None)
    redacted = dict(data)

    system = data.get("system")
    if isinstance(system, list):
        redacted["system"] = _redact_text_blocks(system, mode)
    elif system is not None:
        redacted["system"] = redact_text(system, mode)

    messages = data.get("messages")
    if isinstance(messages, list):
        updated_messages = []
        for message in messages:
            if not isinstance(message, dict):
                updated_messages.append(message)
                continue
            updated = dict(message)
            content = message.get("content")
            if isinstance(content, list):
                updated["content"] = _redact_text_blocks(content, mode)
            elif content is not None:
                updated["content"] = redact_text(content, mode)
            updated_messages.append(updated)
        redacted["messages"] = updated_messages

    tools = data.get("tools")
    if isinstance(tools, list):
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
                updated["parameters"] = _redact_value(updated.get("parameters"), mode)
            updated_tools.append(updated)
        redacted["tools"] = updated_tools

    tool_choice = data.get("tool_choice")
    if isinstance(tool_choice, dict):
        updated_choice = dict(tool_choice)
        if "name" in updated_choice:
            updated_choice["name"] = redact_text(updated_choice.get("name"), mode)
        if "input" in updated_choice:
            updated_choice["input"] = _redact_value(updated_choice.get("input"), mode)
        redacted["tool_choice"] = updated_choice

    return redacted


def redact_anthropic_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    mode = _redaction_mode(None)
    redacted = dict(data)
    content = data.get("content")
    if isinstance(content, list):
        updated_content: List[Dict[str, Any]] = []
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
                    updated["input"] = _redact_value(updated.get("input"), mode)
                updated_content.append(updated)
                continue
            updated_content.append(block)
        redacted["content"] = updated_content
    return redacted


def redact_openai_error(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _normalize_payload(payload)
    if not isinstance(data, dict):
        return {}

    mode = _redaction_mode(None)
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

"""Anthropic error envelope helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional


def _extract_openai_error(openai_error: Any) -> Dict[str, Any]:
    if isinstance(openai_error, dict):
        inner = openai_error.get("error")
        if isinstance(inner, dict):
            return inner
        return openai_error
    return {}


def map_openai_error_type(openai_error: Any, default: str = "api_error") -> str:
    """Map OpenAI error payloads to an Anthropic error type."""

    error_type = _extract_openai_error(openai_error).get("type")
    if isinstance(error_type, str) and error_type:
        return error_type
    return default


def build_anthropic_error(
    status_code: int,
    error_type: Optional[str],
    message: str,
    param: Optional[str] = None,
    code: Optional[str] = None,
    openai_error: Any = None,
) -> Dict[str, Any]:
    """Return Anthropic error envelope with optional OpenAI details."""

    resolved_type = error_type or map_openai_error_type(openai_error)
    return {
        "type": "error",
        "error": {
            "type": resolved_type,
            "message": message,
            "param": param,
            "code": code,
            "openai": openai_error,
        },
    }

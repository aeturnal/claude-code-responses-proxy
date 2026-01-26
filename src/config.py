"""Configuration helpers for OpenAI upstream access."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4.1")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


OBS_LOG_ENABLED = _env_bool("OBS_LOG_ENABLED", False)
OBS_LOG_FILE = os.getenv("OBS_LOG_FILE", "./logs/requests.log")
OBS_REDACTION_MODE = os.getenv("OBS_REDACTION_MODE", "full")
OBS_LOG_PRETTY = _env_bool("OBS_LOG_PRETTY", True)


def require_openai_api_key() -> str:
    """Return the API key or raise if missing."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required")
    return OPENAI_API_KEY


@lru_cache(maxsize=1)
def _load_model_map() -> Dict[str, Any]:
    raw = os.getenv("MODEL_MAP_JSON")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MODEL_MAP_JSON must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("MODEL_MAP_JSON must be a JSON object")
    return parsed


def resolve_openai_model(anthropic_model: str) -> str:
    """Resolve an Anthropic model name to an OpenAI model name."""
    if not anthropic_model:
        raise ValueError("anthropic_model must be provided")
    model_map = _load_model_map()
    if anthropic_model in model_map:
        return model_map[anthropic_model]
    return OPENAI_DEFAULT_MODEL

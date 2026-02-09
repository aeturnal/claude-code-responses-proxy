"""Configuration helpers for OpenAI upstream access."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import structlog
from src.config_model_map import (
    parse_model_map_json,
    resolve_model_from_map,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

# Upstream mode:
# - openai: use OPENAI_API_KEY against OPENAI_BASE_URL (default https://api.openai.com/v1)
# - codex: use ChatGPT/Codex credentials from ~/.codex/auth.json against chatgpt.com backend
OPENAI_UPSTREAM_MODE = os.getenv("OPENAI_UPSTREAM_MODE", "openai").strip().lower()
CODEX_BASE_URL = os.getenv(
    "CODEX_BASE_URL", "https://chatgpt.com/backend-api/codex"
).rstrip("/")
CODEX_AUTH_PATH = os.getenv("CODEX_AUTH_PATH")
CODEX_DEFAULT_INSTRUCTIONS = os.getenv(
    "CODEX_DEFAULT_INSTRUCTIONS", "You are a helpful assistant."
)

logger = structlog.get_logger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


OBS_LOG_ALL = _env_bool("OBS_LOG_ALL", False)
OBS_LOG_ENABLED = _env_bool("OBS_LOG_ENABLED", False) or OBS_LOG_ALL
OBS_LOG_FILE = os.getenv("OBS_LOG_FILE", "./logs/requests.log")
OBS_REDACTION_MODE = os.getenv("OBS_REDACTION_MODE", "full")
OBS_LOG_PRETTY = _env_bool("OBS_LOG_PRETTY", True)
OBS_STREAM_LOG_ENABLED = _env_bool("OBS_STREAM_LOG_ENABLED", OBS_LOG_ENABLED)
if OBS_LOG_ALL:
    OBS_STREAM_LOG_ENABLED = True
OBS_STREAM_LOG_FILE = os.getenv("OBS_STREAM_LOG_FILE", "./logs/streaming.log")
ANTHROPIC_TELEMETRY_LOG_ENABLED = _env_bool("ANTHROPIC_TELEMETRY_LOG_ENABLED", False)
ANTHROPIC_TELEMETRY_LOG_FILE = os.getenv(
    "ANTHROPIC_TELEMETRY_LOG_FILE", "./logs/anthropic_telemetry.log"
)


class MissingUpstreamCredentialsError(ValueError):
    """Raised when upstream credentials are missing."""


def require_openai_api_key() -> str:
    """Return the API key or raise if missing.

    Note: Prefer require_upstream_mode() + require_openai_api_key() for new code.
    """
    if not OPENAI_API_KEY:
        raise MissingUpstreamCredentialsError("OPENAI_API_KEY is required")
    return OPENAI_API_KEY


def require_upstream_mode() -> str:
    mode = (OPENAI_UPSTREAM_MODE or "openai").strip().lower()
    if mode not in {"openai", "codex"}:
        raise ValueError(
            "OPENAI_UPSTREAM_MODE must be 'openai' or 'codex' (got "
            + repr(OPENAI_UPSTREAM_MODE)
            + ")"
        )
    return mode


def get_openai_default_model() -> str:
    return os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5.2")


@lru_cache(maxsize=16)
def _parse_model_map(raw: str | None) -> Dict[str, str]:
    normalized_map, nested_used = parse_model_map_json(raw)

    if OBS_LOG_ENABLED:
        logger.info(
            "model_map_loaded",
            entry_count=len(normalized_map),
            nested=nested_used,
        )

    return normalized_map


def _load_model_map() -> Dict[str, str]:
    return _parse_model_map(os.getenv("MODEL_MAP_JSON"))


def _clear_model_map_cache_for_tests() -> None:
    _parse_model_map.cache_clear()


def resolve_openai_model(anthropic_model: Any) -> str:
    """Resolve an Anthropic model name to an OpenAI model name."""
    model_map = _load_model_map()
    resolved, match_type, normalized_request = resolve_model_from_map(
        anthropic_model, model_map
    )

    if resolved is None:
        resolved = get_openai_default_model()

    if OBS_LOG_ENABLED:
        logger.info(
            "model_resolved",
            model_anthropic=normalized_request,
            match_type=match_type,
            model_openai=resolved,
        )

    return resolved

"""Configuration helpers for OpenAI upstream access."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

import structlog

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

logger = structlog.get_logger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


OBS_LOG_ENABLED = _env_bool("OBS_LOG_ENABLED", False)
OBS_LOG_FILE = os.getenv("OBS_LOG_FILE", "./logs/requests.log")
OBS_REDACTION_MODE = os.getenv("OBS_REDACTION_MODE", "full")
OBS_LOG_PRETTY = _env_bool("OBS_LOG_PRETTY", True)


class MissingOpenAIAPIKeyError(ValueError):
    """Raised when the OpenAI API key is missing."""


def require_openai_api_key() -> str:
    """Return the API key or raise if missing."""
    if not OPENAI_API_KEY:
        raise MissingOpenAIAPIKeyError("OPENAI_API_KEY is required")
    return OPENAI_API_KEY


def get_openai_default_model() -> str:
    return os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5.2")


def _normalize_model_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


@lru_cache(maxsize=16)
def _parse_model_map(raw: str | None) -> Dict[str, str]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MODEL_MAP_JSON must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("MODEL_MAP_JSON must be a JSON object")

    nested_models = parsed.get("models")
    if nested_models is not None:
        if not isinstance(nested_models, dict):
            raise ValueError("MODEL_MAP_JSON['models'] must be a JSON object")
        flat_keys = [k for k in parsed.keys() if k != "models"]
        if flat_keys:
            raise ValueError(
                "MODEL_MAP_JSON cannot contain both top-level mappings and a 'models' object"
            )
        mapping = nested_models
        nested_used = True
    else:
        mapping = parsed
        nested_used = False

    normalized_map: Dict[str, str] = {}
    seen_raw_keys: Dict[str, list[str]] = {}

    for raw_key, raw_value in mapping.items():
        normalized_key = _normalize_model_key(raw_key)
        if normalized_key is None:
            raise ValueError("MODEL_MAP_JSON keys must be non-empty strings")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(
                f"MODEL_MAP_JSON value for '{raw_key}' must be a non-empty string"
            )
        if normalized_key in normalized_map:
            seen_raw_keys.setdefault(normalized_key, []).append(str(raw_key))
        else:
            seen_raw_keys.setdefault(normalized_key, []).append(str(raw_key))
            normalized_map[normalized_key] = raw_value

    collisions = {k: v for k, v in seen_raw_keys.items() if len(v) > 1}
    if collisions:
        parts = [f"{norm}: {raw_keys}" for norm, raw_keys in collisions.items()]
        raise ValueError(
            "MODEL_MAP_JSON has duplicate keys after normalization: " + "; ".join(parts)
        )

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
    normalized_request = _normalize_model_key(anthropic_model)
    model_map = _load_model_map()

    match_type = "miss"
    resolved = None

    if normalized_request is not None:
        resolved = model_map.get(normalized_request)
        if resolved is not None:
            match_type = "exact"
        else:
            matches: list[tuple[str, str]] = [
                (k, v) for k, v in model_map.items() if normalized_request.startswith(k)
            ]
            if matches:
                max_len = max(len(k) for k, _ in matches)
                best = [(k, v) for k, v in matches if len(k) == max_len]
                if len(best) > 1:
                    keys = sorted(k for k, _ in best)
                    raise ValueError(
                        "MODEL_MAP_JSON prefix mapping is ambiguous for "
                        f"'{normalized_request}': {keys}"
                    )
                resolved = best[0][1]
                match_type = "prefix"

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

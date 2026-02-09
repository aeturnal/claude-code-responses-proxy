"""Shared redaction primitives and constants."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional, Tuple

import structlog

from src.config import OBS_REDACTION_MODE

REDACTION_TOKEN = "[REDACTED]"
LOG_ARRAY_LIMIT = 50
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "email",
    "jwt",
    "password",
    "phone",
    "secret",
    "session",
    "set_cookie",
    "token",
}

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_presidio_engines() -> Tuple[Optional[Any], Optional[Any]]:
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except BaseException as exc:  # pragma: no cover - defensive fallback
        logger.warning("presidio_import_failed", error=str(exc))
        return None, None
    try:
        return AnalyzerEngine(), AnonymizerEngine()
    except BaseException as exc:  # pragma: no cover - defensive fallback
        logger.warning("presidio_init_failed", error=str(exc))
        return None, None


def redaction_mode(override: Optional[str] = None) -> str:
    mode = (override or OBS_REDACTION_MODE or "full").strip().lower()
    if mode not in {"full", "partial", "none"}:
        return "full"
    return mode


def redact_text(text: Any, mode: Optional[str] = None) -> Any:
    """Redact a string value, optionally with partial redaction."""

    if not isinstance(text, str):
        return text

    mode = redaction_mode(mode)
    if mode == "none":
        return text
    if mode == "full":
        return REDACTION_TOKEN

    try:
        analyzer, anonymizer = get_presidio_engines()
        if analyzer is None or anonymizer is None:
            return REDACTION_TOKEN
        results = analyzer.analyze(text=text, language="en")
        if not results:
            return text
        from presidio_anonymizer.entities import OperatorConfig

        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,  # type: ignore[arg-type]
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": REDACTION_TOKEN})
            },
        )
        return anonymized.text
    except BaseException:
        return REDACTION_TOKEN


def normalize_payload(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if hasattr(payload, "dict"):
        return payload.dict(exclude_none=True)
    return payload


def redact_value(value: Any, mode: Optional[str]) -> Any:
    if isinstance(value, str):
        return redact_text(value, mode)
    if isinstance(value, list):
        return [redact_value(item, mode) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(val, mode) for key, val in value.items()}
    return value


def truncate_list(items: List[Any], limit: int) -> tuple[List[Any], bool]:
    if limit <= 0:
        return [], bool(items)
    if len(items) <= limit:
        return items, False
    return items[:limit], True


def normalize_key(key: Any) -> Optional[str]:
    if not isinstance(key, str):
        return None
    return key.strip().lower().replace("-", "_")

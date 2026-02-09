"""Shared helpers for /v1/messages handlers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from asgi_correlation_id import correlation_id
from fastapi import Request

from src.config import resolve_openai_model
from src.errors.anthropic_error import build_anthropic_error, map_openai_error_type
from src.observability.logging import logging_enabled
from src.observability.redaction import (
    redact_generic_payload,
    redact_messages_request,
    redact_openai_error,
    summarize_messages_request,
)
from src.transport.openai_client import OpenAIUpstreamError


@dataclass(frozen=True)
class MessageRequestContext:
    model_anthropic: str
    model_openai: Optional[str]
    correlation_id: Optional[str]
    payload_summary: Optional[Dict[str, Any]]


def extract_openai_error_fields(openai_error: Any) -> Dict[str, Optional[str]]:
    if isinstance(openai_error, dict):
        error_obj = openai_error.get("error")
        if isinstance(error_obj, dict):
            return {
                "message": error_obj.get("message"),
                "param": error_obj.get("param"),
                "code": error_obj.get("code"),
            }
    return {"message": None, "param": None, "code": None}


def normalize_openai_payload(payload: Any) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if hasattr(payload, "dict"):
        return payload.dict(exclude_none=True)
    return payload


def get_correlation_id(request: Request) -> Optional[str]:
    return getattr(request.state, "correlation_id", None) or correlation_id.get()


def duration_ms(request: Request) -> Optional[int]:
    start_time = getattr(request.state, "start_time", None)
    if start_time is None:
        return None
    return int((time.perf_counter() - start_time) * 1000)


def parse_sse_payload(payload: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    event_name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    for line in payload.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
            continue
        if line.startswith("data:"):
            raw = line[len("data:") :].strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                data = parsed
    return event_name, data


def format_sse_error(payload: Dict[str, Any]) -> str:
    return f"event: error\ndata: {json.dumps(payload)}\n\n"


def prepare_request_context(
    logger: Any,
    http_request: Request,
    request: Any,
    include_stream_logging: bool = False,
) -> MessageRequestContext:
    model_anthropic = request.model
    model_openai = None
    try:
        model_openai = resolve_openai_model(request.model)
    except ValueError:
        model_openai = None

    correlation_id_value = get_correlation_id(http_request)
    payload_summary: Optional[Dict[str, Any]] = None
    if logging_enabled() or include_stream_logging:
        payload_summary = summarize_messages_request(request)

    if logging_enabled():
        tool_use_count = (
            payload_summary.get("tool_use_count", 0) if payload_summary else 0
        )
        if isinstance(tool_use_count, int) and tool_use_count >= 40:
            logger.warning(
                "tool_use_spike",
                endpoint=str(http_request.url.path),
                correlation_id=correlation_id_value,
                model_anthropic=model_anthropic,
                model_openai=model_openai,
                payload_summary=payload_summary,
            )
        logger.info(
            "request",
            endpoint=str(http_request.url.path),
            method=http_request.method,
            correlation_id=correlation_id_value,
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            payload=redact_messages_request(request),
            payload_summary=payload_summary,
        )

    return MessageRequestContext(
        model_anthropic=model_anthropic,
        model_openai=model_openai,
        correlation_id=correlation_id_value,
        payload_summary=payload_summary,
    )


def log_upstream_request(
    logger: Any,
    http_request: Request,
    context: MessageRequestContext,
    payload: Dict[str, Any],
) -> None:
    if not logging_enabled():
        return
    logger.debug(
        "upstream_request",
        endpoint=str(http_request.url.path),
        correlation_id=context.correlation_id,
        model_anthropic=context.model_anthropic,
        model_openai=context.model_openai,
        payload=redact_generic_payload(payload),
    )


def log_error(
    logger: Any,
    http_request: Request,
    context: MessageRequestContext,
    status_code: int,
    payload: Dict[str, Any],
) -> None:
    if not logging_enabled():
        return
    logger.info(
        "error",
        endpoint=str(http_request.url.path),
        status_code=status_code,
        duration_ms=duration_ms(http_request),
        correlation_id=context.correlation_id,
        model_anthropic=context.model_anthropic,
        model_openai=context.model_openai,
        payload=redact_openai_error(payload),
    )


def log_success_response(
    logger: Any,
    http_request: Request,
    context: MessageRequestContext,
    token_usage: Optional[Dict[str, Any]],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    if not logging_enabled():
        return
    log_data: Dict[str, Any] = {
        "endpoint": str(http_request.url.path),
        "status_code": 200,
        "duration_ms": duration_ms(http_request),
        "correlation_id": context.correlation_id,
        "model_anthropic": context.model_anthropic,
        "model_openai": context.model_openai,
        "token_usage": token_usage,
    }
    if payload is not None:
        log_data["payload"] = payload
    logger.info("response", **log_data)


def build_missing_credentials_error(exc: Exception) -> tuple[int, Dict[str, Any], Dict[str, Any]]:
    message = str(exc) or "Missing upstream credentials"
    openai_error = {"error": {"message": message}}
    error_payload = build_anthropic_error(
        401,
        "authentication_error",
        message,
        openai_error=openai_error,
    )
    return 401, error_payload, openai_error


def build_upstream_error(exc: OpenAIUpstreamError) -> tuple[int, Dict[str, Any], Dict[str, Any]]:
    error_fields = extract_openai_error_fields(exc.error_payload)
    error_type = map_openai_error_type(exc.error_payload)
    message = error_fields.get("message") or "OpenAI upstream error"
    error_payload = build_anthropic_error(
        exc.status_code,
        error_type,
        message,
        param=error_fields.get("param"),
        code=error_fields.get("code"),
        openai_error=exc.error_payload,
    )
    return exc.status_code, error_payload, exc.error_payload

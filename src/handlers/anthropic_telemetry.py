"""Anthropic telemetry batch endpoint."""

from __future__ import annotations

import json
from typing import Any, Optional

from asgi_correlation_id import correlation_id
from fastapi import APIRouter, Request, Response

from src.observability.logging import (
    anthropic_telemetry_logging_enabled,
    get_anthropic_telemetry_logger,
)
from src.observability.redaction import redact_generic_payload, redact_text

router = APIRouter()


def _get_correlation_id(request: Request) -> Optional[str]:
    return getattr(request.state, "correlation_id", None) or correlation_id.get()


def _get_client_ip(request: Request) -> Optional[str]:
    if request.client:
        return request.client.host
    return None


@router.post("/api/event_logging/batch")
async def handle_telemetry_batch(request: Request) -> Response:
    telemetry_enabled = anthropic_telemetry_logging_enabled()
    body = b""
    if telemetry_enabled:
        body = await request.body()
    content_type = request.headers.get("content-type")
    content_length = request.headers.get("content-length")
    user_agent = request.headers.get("user-agent")
    forwarded_for = request.headers.get("x-forwarded-for")
    correlation_id_value = _get_correlation_id(request)
    client_ip = _get_client_ip(request)

    payload_redacted: Optional[Any] = None
    body_redacted: Optional[Any] = None
    parse_ok: Optional[bool] = None

    if telemetry_enabled and content_type and "application/json" in content_type:
        try:
            parsed = json.loads(body)
            payload_redacted = redact_generic_payload(parsed)
            parse_ok = True
        except json.JSONDecodeError:
            parse_ok = False
    if telemetry_enabled and parse_ok is False:
        try:
            text_body = body.decode("utf-8", errors="replace")
        except Exception:
            text_body = ""
        body_redacted = redact_text(text_body)

    telemetry_logger = get_anthropic_telemetry_logger()
    telemetry_logger.info(
        "anthropic_telemetry_batch",
        endpoint=str(request.url.path),
        method=request.method,
        correlation_id=correlation_id_value,
        client_ip=client_ip,
        forwarded_for=forwarded_for,
        user_agent=user_agent,
        content_type=content_type,
        content_length=content_length,
        payload_logged=telemetry_enabled,
        parse_ok=parse_ok,
        payload_redacted=payload_redacted,
        body_redacted=body_redacted,
    )

    return Response(status_code=204)

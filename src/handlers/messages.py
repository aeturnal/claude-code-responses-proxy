"""/v1/messages handler."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, Optional

import structlog
from asgi_correlation_id import correlation_id
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.errors.anthropic_error import build_anthropic_error, map_openai_error_type
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.mapping.openai_stream_to_anthropic import translate_openai_events
from src.mapping.openai_to_anthropic import map_openai_response_to_anthropic
from src.observability.logging import logging_enabled
from src.observability.redaction import (
    redact_anthropic_response,
    redact_messages_request,
    redact_openai_error,
)
from src.schema.anthropic import MessagesRequest
from src.transport.openai_client import OpenAIUpstreamError, create_openai_response
from src.transport.openai_stream import stream_openai_events

router = APIRouter()
logger = structlog.get_logger(__name__)


def _extract_openai_error_fields(openai_error: Any) -> Dict[str, Optional[str]]:
    if isinstance(openai_error, dict):
        error_obj = openai_error.get("error")
        if isinstance(error_obj, dict):
            return {
                "message": error_obj.get("message"),
                "param": error_obj.get("param"),
                "code": error_obj.get("code"),
            }
    return {"message": None, "param": None, "code": None}


def _normalize_openai_payload(payload: Any) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if hasattr(payload, "dict"):
        return payload.dict(exclude_none=True)
    return payload


def _get_correlation_id(request: Request) -> Optional[str]:
    return getattr(request.state, "correlation_id", None) or correlation_id.get()


def _duration_ms(request: Request) -> Optional[int]:
    start_time = getattr(request.state, "start_time", None)
    if start_time is None:
        return None
    return int((time.perf_counter() - start_time) * 1000)


@router.post("/v1/messages")
async def create_message(http_request: Request, request: MessagesRequest) -> Any:
    """Translate Anthropic Messages request into OpenAI Responses output."""

    correlation_id_value = _get_correlation_id(http_request)
    if logging_enabled():
        logger.info(
            "request",
            endpoint=str(http_request.url.path),
            method=http_request.method,
            correlation_id=correlation_id_value,
            payload=redact_messages_request(request),
        )

    openai_request = map_anthropic_request_to_openai(request)
    payload = _normalize_openai_payload(openai_request)
    try:
        response = await create_openai_response(payload)
    except OpenAIUpstreamError as exc:
        error_fields = _extract_openai_error_fields(exc.error_payload)
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
        if logging_enabled():
            logger.info(
                "error",
                endpoint=str(http_request.url.path),
                status_code=exc.status_code,
                duration_ms=_duration_ms(http_request),
                correlation_id=correlation_id_value,
                payload=redact_openai_error(exc.error_payload),
            )
        return JSONResponse(status_code=exc.status_code, content=error_payload)

    response_payload = map_openai_response_to_anthropic(response)
    if logging_enabled():
        logger.info(
            "response",
            endpoint=str(http_request.url.path),
            status_code=200,
            duration_ms=_duration_ms(http_request),
            correlation_id=correlation_id_value,
            token_usage=response.get("usage") if isinstance(response, dict) else None,
            payload=redact_anthropic_response(response_payload),
        )
    return response_payload


@router.post("/v1/messages/stream")
async def stream_messages(
    http_request: Request, request: MessagesRequest
) -> StreamingResponse:
    """Stream Anthropic-compatible SSE events mapped from OpenAI Responses."""
    openai_request = map_anthropic_request_to_openai(request)
    payload = _normalize_openai_payload(openai_request)
    payload["stream"] = True

    async def event_stream() -> AsyncIterator[str]:
        openai_events = stream_openai_events(payload)
        async for sse_event in translate_openai_events(openai_events):
            yield sse_event

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )

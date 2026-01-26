"""/v1/messages handler."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Dict, Optional

import structlog
from asgi_correlation_id import correlation_id
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.config import MissingOpenAIAPIKeyError
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


def _parse_sse_payload(payload: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
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


def _format_sse_error(payload: Dict[str, Any]) -> str:
    return f"event: error\ndata: {json.dumps(payload)}\n\n"


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
    except MissingOpenAIAPIKeyError:
        openai_error = {"error": {"message": "OPENAI_API_KEY is required"}}
        error_payload = build_anthropic_error(
            401,
            "authentication_error",
            "OPENAI_API_KEY is required",
            openai_error=openai_error,
        )
        if logging_enabled():
            logger.info(
                "error",
                endpoint=str(http_request.url.path),
                status_code=401,
                duration_ms=_duration_ms(http_request),
                correlation_id=correlation_id_value,
                payload=redact_openai_error(openai_error),
            )
        return JSONResponse(status_code=401, content=error_payload)
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
    payload["stream"] = True

    async def event_stream() -> AsyncIterator[str]:
        latest_usage: Optional[Dict[str, Any]] = None
        stream_failed = False
        try:
            openai_events = stream_openai_events(payload)
            async for sse_event in translate_openai_events(openai_events):
                event_name, data = _parse_sse_payload(sse_event)
                if event_name == "message_delta" and data is not None:
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        latest_usage = usage
                yield sse_event
        except MissingOpenAIAPIKeyError:
            stream_failed = True
            openai_error = {"error": {"message": "OPENAI_API_KEY is required"}}
            error_payload = build_anthropic_error(
                401,
                "authentication_error",
                "OPENAI_API_KEY is required",
                openai_error=openai_error,
            )
            if logging_enabled():
                logger.info(
                    "error",
                    endpoint=str(http_request.url.path),
                    status_code=401,
                    duration_ms=_duration_ms(http_request),
                    correlation_id=correlation_id_value,
                    payload=redact_openai_error(openai_error),
                )
            yield _format_sse_error(error_payload)
        except OpenAIUpstreamError as exc:
            stream_failed = True
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
            yield _format_sse_error(error_payload)
        finally:
            if logging_enabled() and not stream_failed:
                logger.info(
                    "response",
                    endpoint=str(http_request.url.path),
                    status_code=200,
                    duration_ms=_duration_ms(http_request),
                    correlation_id=correlation_id_value,
                    token_usage=latest_usage,
                )

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )

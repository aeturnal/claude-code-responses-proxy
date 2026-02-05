"""/v1/messages handler."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, Optional

import structlog
from asgi_correlation_id import correlation_id
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.config import MissingUpstreamCredentialsError, resolve_openai_model
from src.errors.anthropic_error import build_anthropic_error, map_openai_error_type
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.mapping.openai_stream_to_anthropic import translate_openai_events
from src.mapping.openai_to_anthropic import map_openai_response_to_anthropic
from src.observability.logging import (
    get_stream_logger,
    logging_enabled,
    streaming_logging_enabled,
)
from src.observability.redaction import (
    redact_anthropic_response,
    redact_generic_payload,
    redact_messages_request,
    redact_openai_error,
    summarize_messages_request,
)
from src.schema.anthropic import MessagesRequest
from src.token_counting.openai_count import count_openai_request_tokens
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

    if request.stream:
        return await stream_messages(http_request, request)

    model_anthropic = request.model
    model_openai = None
    try:
        model_openai = resolve_openai_model(request.model)
    except ValueError:
        model_openai = None
    correlation_id_value = _get_correlation_id(http_request)
    payload_summary: Optional[Dict[str, Any]] = None
    if logging_enabled():
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

    openai_request = map_anthropic_request_to_openai(request)
    payload = _normalize_openai_payload(openai_request)
    if logging_enabled():
        logger.debug(
            "upstream_request",
            endpoint=str(http_request.url.path),
            correlation_id=correlation_id_value,
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            payload=redact_generic_payload(payload),
        )
    try:
        response = await create_openai_response(payload)
    except MissingUpstreamCredentialsError as exc:
        message = str(exc) or "Missing upstream credentials"
        openai_error = {"error": {"message": message}}
        error_payload = build_anthropic_error(
            401,
            "authentication_error",
            message,
            openai_error=openai_error,
        )
        if logging_enabled():
            logger.info(
                "error",
                endpoint=str(http_request.url.path),
                status_code=401,
                duration_ms=_duration_ms(http_request),
                correlation_id=correlation_id_value,
                model_anthropic=model_anthropic,
                model_openai=model_openai,
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
                model_anthropic=model_anthropic,
                model_openai=model_openai,
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
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            token_usage=response.get("usage") if isinstance(response, dict) else None,
            payload=redact_anthropic_response(response_payload),
        )
    return response_payload


@router.post("/v1/messages/stream")
async def stream_messages(
    http_request: Request, request: MessagesRequest
) -> StreamingResponse:
    """Stream Anthropic-compatible SSE events mapped from OpenAI Responses."""
    model_anthropic = request.model
    model_openai = None
    try:
        model_openai = resolve_openai_model(request.model)
    except ValueError:
        model_openai = None
    correlation_id_value = _get_correlation_id(http_request)
    stream_logging_enabled = streaming_logging_enabled()
    payload_summary: Optional[Dict[str, Any]] = None
    if logging_enabled() or stream_logging_enabled:
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

    stream_logger = get_stream_logger() if stream_logging_enabled else None
    stream_start = time.perf_counter() if stream_logger else None
    if stream_logger:
        stream_logger.info(
            "stream_start",
            endpoint=str(http_request.url.path),
            correlation_id=correlation_id_value,
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            payload_summary=payload_summary,
        )

    openai_request = map_anthropic_request_to_openai(request)
    payload = _normalize_openai_payload(openai_request)
    payload["stream"] = True
    if logging_enabled():
        logger.debug(
            "upstream_request",
            endpoint=str(http_request.url.path),
            correlation_id=correlation_id_value,
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            payload=redact_generic_payload(payload),
        )
    initial_usage: Optional[Dict[str, Any]] = None
    try:
        input_tokens = count_openai_request_tokens(payload)
    except ValueError:
        input_tokens = None
    if isinstance(input_tokens, int):
        initial_usage = {"input_tokens": input_tokens, "output_tokens": 0}

    async def event_stream() -> AsyncIterator[str]:
        latest_usage: Optional[Dict[str, Any]] = None
        stream_failed = False
        saw_message_start = False
        first_event_name: Optional[str] = None
        first_event_at: Optional[float] = None
        event_count = 0
        byte_count = 0
        error_status: Optional[int] = None
        error_type: Optional[str] = None
        error_message: Optional[str] = None
        if stream_logger:
            stream_logger.info(
                "stream_enter",
                endpoint=str(http_request.url.path),
                correlation_id=correlation_id_value,
                model_anthropic=model_anthropic,
                model_openai=model_openai,
            )
        try:
            openai_events = stream_openai_events(payload)
            async for sse_event in translate_openai_events(
                openai_events,
                initial_usage=initial_usage,
                model_override=model_anthropic,
            ):
                event_name, data = _parse_sse_payload(sse_event)
                if first_event_at is None:
                    first_event_at = time.perf_counter()
                if first_event_name is None and event_name:
                    first_event_name = event_name
                if event_name == "message_start":
                    saw_message_start = True
                if event_name == "message_delta" and data is not None:
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        latest_usage = usage
                event_count += 1
                if stream_logger:
                    byte_count += len(sse_event)
                yield sse_event
        except asyncio.CancelledError:
            stream_failed = True
            error_status = 499
            error_type = "client_disconnect"
            error_message = "stream cancelled"
            raise
        except MissingUpstreamCredentialsError as exc:
            stream_failed = True
            error_status = 401
            error_type = "authentication_error"
            error_message = str(exc) or "Missing upstream credentials"
            openai_error = {"error": {"message": error_message}}
            error_payload = build_anthropic_error(
                401,
                "authentication_error",
                error_message,
                openai_error=openai_error,
            )
            if logging_enabled():
                logger.info(
                    "error",
                    endpoint=str(http_request.url.path),
                    status_code=401,
                    duration_ms=_duration_ms(http_request),
                    correlation_id=correlation_id_value,
                    model_anthropic=model_anthropic,
                    model_openai=model_openai,
                    payload=redact_openai_error(openai_error),
                )
            yield _format_sse_error(error_payload)
        except OpenAIUpstreamError as exc:
            stream_failed = True
            error_fields = _extract_openai_error_fields(exc.error_payload)
            error_type = map_openai_error_type(exc.error_payload)
            message = error_fields.get("message") or "OpenAI upstream error"
            error_status = exc.status_code
            error_message = message
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
                    model_anthropic=model_anthropic,
                    model_openai=model_openai,
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
                    model_anthropic=model_anthropic,
                    model_openai=model_openai,
                    token_usage=latest_usage,
                )
            if stream_logger:
                duration_ms = None
                time_to_first_event_ms = None
                if stream_start is not None:
                    duration_ms = int((time.perf_counter() - stream_start) * 1000)
                    if first_event_at is not None:
                        time_to_first_event_ms = int(
                            (first_event_at - stream_start) * 1000
                        )
                stream_logger.info(
                    "stream_end",
                    endpoint=str(http_request.url.path),
                    correlation_id=correlation_id_value,
                    model_anthropic=model_anthropic,
                    model_openai=model_openai,
                    duration_ms=duration_ms,
                    time_to_first_event_ms=time_to_first_event_ms,
                    event_count=event_count,
                    byte_count=byte_count,
                    first_event_name=first_event_name,
                    saw_message_start=saw_message_start,
                    stream_failed=stream_failed,
                    error_status=error_status,
                    error_type=error_type,
                    error_message=error_message,
                    token_usage=latest_usage,
                )

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )

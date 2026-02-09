"""/v1/messages handler."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Dict, Optional

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.config import MissingUpstreamCredentialsError
from src.handlers.messages_common import (
    build_missing_credentials_error,
    build_upstream_error,
    format_sse_error,
    log_error,
    log_success_response,
    log_upstream_request,
    normalize_openai_payload,
    parse_sse_payload,
    prepare_request_context,
)
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.mapping.openai_stream_to_anthropic import translate_openai_events
from src.mapping.openai_to_anthropic import map_openai_response_to_anthropic
from src.observability.logging import (
    get_stream_logger,
    streaming_logging_enabled,
)
from src.observability.redaction import (
    redact_anthropic_response,
)
from src.schema.anthropic import MessagesRequest
from src.token_counting.openai_count import count_openai_request_tokens
from src.transport.openai_client import OpenAIUpstreamError, create_openai_response
from src.transport.openai_stream import stream_openai_events

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/v1/messages")
async def create_message(http_request: Request, request: MessagesRequest) -> Any:
    """Translate Anthropic Messages request into OpenAI Responses output."""

    if request.stream:
        return await stream_messages(http_request, request)

    context = prepare_request_context(logger, http_request, request)

    openai_request = map_anthropic_request_to_openai(request)
    payload = normalize_openai_payload(openai_request)
    log_upstream_request(logger, http_request, context, payload)
    try:
        response = await create_openai_response(payload)
    except MissingUpstreamCredentialsError as exc:
        status_code, error_payload, error_source = build_missing_credentials_error(exc)
        log_error(logger, http_request, context, status_code, error_source)
        return JSONResponse(status_code=status_code, content=error_payload)
    except OpenAIUpstreamError as exc:
        status_code, error_payload, error_source = build_upstream_error(exc)
        log_error(logger, http_request, context, status_code, error_source)
        return JSONResponse(status_code=status_code, content=error_payload)

    response_payload = map_openai_response_to_anthropic(response)
    log_success_response(
        logger,
        http_request,
        context,
        token_usage=response.get("usage") if isinstance(response, dict) else None,
        payload=redact_anthropic_response(response_payload),
    )
    return response_payload


@router.post("/v1/messages/stream")
async def stream_messages(
    http_request: Request, request: MessagesRequest
) -> StreamingResponse:
    """Stream Anthropic-compatible SSE events mapped from OpenAI Responses."""
    stream_logging_enabled = streaming_logging_enabled()
    context = prepare_request_context(
        logger,
        http_request,
        request,
        include_stream_logging=stream_logging_enabled,
    )

    stream_logger = get_stream_logger() if stream_logging_enabled else None
    stream_start = time.perf_counter() if stream_logger else None
    if stream_logger:
        stream_logger.info(
            "stream_start",
            endpoint=str(http_request.url.path),
            correlation_id=context.correlation_id,
            model_anthropic=context.model_anthropic,
            model_openai=context.model_openai,
            payload_summary=context.payload_summary,
        )

    openai_request = map_anthropic_request_to_openai(request)
    payload = normalize_openai_payload(openai_request)
    payload["stream"] = True
    log_upstream_request(logger, http_request, context, payload)
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
                correlation_id=context.correlation_id,
                model_anthropic=context.model_anthropic,
                model_openai=context.model_openai,
            )
        try:
            openai_events = stream_openai_events(payload)
            async for sse_event in translate_openai_events(
                openai_events,
                initial_usage=initial_usage,
                model_override=context.model_anthropic,
            ):
                event_name, data = parse_sse_payload(sse_event)
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
            status_code, error_payload, error_source = build_missing_credentials_error(
                exc
            )
            error_message = str(exc) or "Missing upstream credentials"
            log_error(logger, http_request, context, status_code, error_source)
            yield format_sse_error(error_payload)
        except OpenAIUpstreamError as exc:
            stream_failed = True
            status_code, error_payload, error_source = build_upstream_error(exc)
            error_status = status_code
            error_data = error_payload.get("error", {})
            if isinstance(error_data, dict):
                resolved_error_type = error_data.get("type")
                resolved_error_message = error_data.get("message")
            else:
                resolved_error_type = None
                resolved_error_message = None
            error_type = (
                resolved_error_type
                if isinstance(resolved_error_type, str)
                else "api_error"
            )
            error_message = (
                resolved_error_message
                if isinstance(resolved_error_message, str)
                else "OpenAI upstream error"
            )
            log_error(logger, http_request, context, status_code, error_source)
            yield format_sse_error(error_payload)
        finally:
            if not stream_failed:
                log_success_response(
                    logger,
                    http_request,
                    context,
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
                    correlation_id=context.correlation_id,
                    model_anthropic=context.model_anthropic,
                    model_openai=context.model_openai,
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

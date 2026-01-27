"""/v1/messages/count_tokens handler."""

from __future__ import annotations

import time

import structlog
from asgi_correlation_id import correlation_id
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.config import resolve_openai_model
from src.errors.anthropic_error import build_anthropic_error
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.observability.logging import logging_enabled
from src.observability.redaction import (
    redact_messages_request,
    redact_openai_error,
    summarize_messages_request,
)
from src.schema.anthropic import CountTokensResponse, MessagesRequest
from src.token_counting.openai_count import count_openai_request_tokens

router = APIRouter()
logger = structlog.get_logger(__name__)


def _get_correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None) or correlation_id.get()


def _duration_ms(request: Request) -> int | None:
    start_time = getattr(request.state, "start_time", None)
    if start_time is None:
        return None
    return int((time.perf_counter() - start_time) * 1000)


@router.post("/v1/messages/count_tokens", response_model=CountTokensResponse)
@router.post("/v1/messages/token_count", response_model=CountTokensResponse)
async def count_tokens(http_request: Request, request: MessagesRequest):
    """Return OpenAI-aligned input token counts for an Anthropic request."""

    model_anthropic = request.model
    model_openai = None
    try:
        model_openai = resolve_openai_model(request.model)
    except ValueError:
        model_openai = None
    correlation_id_value = _get_correlation_id(http_request)
    if logging_enabled():
        logger.info(
            "request",
            endpoint=str(http_request.url.path),
            method=http_request.method,
            correlation_id=correlation_id_value,
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            payload=redact_messages_request(request),
            payload_summary=summarize_messages_request(request),
        )

    try:
        openai_request = map_anthropic_request_to_openai(request)
        input_tokens = count_openai_request_tokens(openai_request)
    except ValueError as exc:
        error_payload = build_anthropic_error(
            400,
            "invalid_request_error",
            str(exc) or "Invalid request",
        )
        if logging_enabled():
            logger.info(
                "error",
                endpoint=str(http_request.url.path),
                status_code=400,
                duration_ms=_duration_ms(http_request),
                correlation_id=correlation_id_value,
                model_anthropic=model_anthropic,
                model_openai=model_openai,
                payload=redact_openai_error(error_payload),
            )
        return JSONResponse(status_code=400, content=error_payload)

    response_payload = CountTokensResponse(input_tokens=input_tokens)
    if logging_enabled():
        logger.info(
            "response",
            endpoint=str(http_request.url.path),
            status_code=200,
            duration_ms=_duration_ms(http_request),
            correlation_id=correlation_id_value,
            model_anthropic=model_anthropic,
            model_openai=model_openai,
            token_usage={"input_tokens": input_tokens},
            payload={"input_tokens": input_tokens},
        )
    return response_payload

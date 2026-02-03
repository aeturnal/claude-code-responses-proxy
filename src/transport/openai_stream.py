"""OpenAI Responses API streaming transport client."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from asgi_correlation_id import correlation_id

from src.config import OPENAI_BASE_URL, require_openai_api_key
from src.observability.logging import get_stream_logger, streaming_logging_enabled
from src.transport.openai_client import OpenAIUpstreamError
from src.transport.lmstudio import (
    collapse_payload,
    is_lmstudio_base_url,
    normalize_payload,
)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"error": {"message": response.text}}


def _parse_data(data_lines: List[str]) -> Any:
    raw = "\n".join(data_lines)
    if raw == "":
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def stream_openai_events(
    payload: Dict[str, Any],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream OpenAI Responses API events as parsed SSE frames."""
    stream_logger = get_stream_logger() if streaming_logging_enabled() else None
    api_key = require_openai_api_key()
    url = f"{OPENAI_BASE_URL}/responses"
    headers = {"Authorization": f"Bearer {api_key}"}
    upstream_correlation_id = correlation_id.get()
    if upstream_correlation_id:
        headers["X-Correlation-ID"] = upstream_correlation_id

    payload = dict(payload)
    payload["stream"] = True

    current_event: Optional[str] = None
    data_lines: List[str] = []

    if stream_logger:
        stream_logger.info(
            "upstream_connect_start",
            endpoint="/v1/messages/stream",
            upstream_url=url,
            correlation_id=upstream_correlation_id,
        )

    async def _run_stream(
        response: httpx.Response,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        nonlocal current_event, data_lines
        async for line in response.aiter_lines():
            if line == "":
                if current_event is None and not data_lines:
                    continue
                event_name = current_event or "message"
                yield {"event": event_name, "data": _parse_data(data_lines)}
                current_event = None
                data_lines = []
                continue

            if line.startswith(":"):
                continue

            if line.startswith("event:"):
                current_event = line[len("event:") :].lstrip()
                continue

            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].lstrip())
                continue

        if current_event is not None or data_lines:
            event_name = current_event or "message"
            yield {"event": event_name, "data": _parse_data(data_lines)}

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            if response.is_error:
                await response.aread()
                error_payload = _safe_json(response)
                if (
                    response.status_code == 400
                    and _is_invalid_input_union(error_payload)
                    and is_lmstudio_base_url()
                ):
                    fallback_payload = normalize_payload(payload)
                    if fallback_payload != payload:
                        if stream_logger:
                            stream_logger.info(
                                "lmstudio_payload_normalized",
                                endpoint="/v1/messages/stream",
                                upstream_url=url,
                                correlation_id=upstream_correlation_id,
                            )
                        current_event = None
                        data_lines = []
                        async with client.stream(
                            "POST", url, json=fallback_payload, headers=headers
                        ) as fallback_response:
                            if not fallback_response.is_error:
                                if stream_logger:
                                    stream_logger.info(
                                        "upstream_connect_ok",
                                        endpoint="/v1/messages/stream",
                                        upstream_url=url,
                                        correlation_id=upstream_correlation_id,
                                        status_code=fallback_response.status_code,
                                    )
                                async for event in _run_stream(fallback_response):
                                    yield event
                                return
                            await fallback_response.aread()
                            error_payload = _safe_json(fallback_response)

                    collapsed_payload = collapse_payload(payload)
                    if (
                        collapsed_payload != payload
                        and collapsed_payload != fallback_payload
                    ):
                        if stream_logger:
                            stream_logger.info(
                                "lmstudio_payload_collapsed",
                                endpoint="/v1/messages/stream",
                                upstream_url=url,
                                correlation_id=upstream_correlation_id,
                            )
                        current_event = None
                        data_lines = []
                        async with client.stream(
                            "POST", url, json=collapsed_payload, headers=headers
                        ) as collapsed_response:
                            if collapsed_response.is_error:
                                await collapsed_response.aread()
                                if stream_logger:
                                    stream_logger.info(
                                        "upstream_connect_error",
                                        endpoint="/v1/messages/stream",
                                        upstream_url=url,
                                        correlation_id=upstream_correlation_id,
                                        status_code=collapsed_response.status_code,
                                    )
                                raise OpenAIUpstreamError(
                                    collapsed_response.status_code,
                                    _safe_json(collapsed_response),
                                )
                            if stream_logger:
                                stream_logger.info(
                                    "upstream_connect_ok",
                                    endpoint="/v1/messages/stream",
                                    upstream_url=url,
                                    correlation_id=upstream_correlation_id,
                                    status_code=collapsed_response.status_code,
                                )
                            async for event in _run_stream(collapsed_response):
                                yield event
                            return

                if stream_logger:
                    stream_logger.info(
                        "upstream_connect_error",
                        endpoint="/v1/messages/stream",
                        upstream_url=url,
                        correlation_id=upstream_correlation_id,
                        status_code=response.status_code,
                    )
                raise OpenAIUpstreamError(response.status_code, error_payload)

            if stream_logger:
                stream_logger.info(
                    "upstream_connect_ok",
                    endpoint="/v1/messages/stream",
                    upstream_url=url,
                    correlation_id=upstream_correlation_id,
                    status_code=response.status_code,
                )

            async for event in _run_stream(response):
                yield event


def _is_invalid_input_union(error_payload: Any) -> bool:
    if not isinstance(error_payload, dict):
        return False
    error = error_payload.get("error")
    if not isinstance(error, dict):
        return False
    if error.get("param") != "input":
        return False
    if error.get("code") != "invalid_union":
        return False
    return True

"""OpenAI Responses API streaming transport client."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from src import config
from src.observability.logging import get_stream_logger, streaming_logging_enabled
from src.transport.lmstudio import collapse_payload, is_lmstudio_base_url, normalize_payload
from src.transport.openai_client import OpenAIUpstreamError
from src.transport.upstream_common import (
    build_upstream_request as _build_upstream_request,
    get_codex_manager as _codex_manager,
    is_invalid_input_union as _is_invalid_input_union,
    rewrite_codex_message_span_types as _rewrite_codex_message_span_types,
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

    payload = dict(payload)
    payload["stream"] = True
    if config.require_upstream_mode() == "codex":
        # ChatGPT Codex backend requires store=false.
        payload.setdefault("store", False)

        # ChatGPT Codex backend does not accept max_output_tokens/max_tokens.
        payload.pop("max_output_tokens", None)
        payload.pop("max_tokens", None)

        # ChatGPT Codex backend does not accept max_tool_calls.
        payload.pop("max_tool_calls", None)

        # ChatGPT Codex backend appears to require instructions on all requests.
        if not payload.get("instructions"):
            payload["instructions"] = config.CODEX_DEFAULT_INSTRUCTIONS

        # ChatGPT Codex backend expects assistant history spans to use output_text.
        _rewrite_codex_message_span_types(payload)

    current_event: Optional[str] = None
    data_lines: List[str] = []

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

    async def _connect_and_stream(
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        stream_payload: dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async with client.stream("POST", url, json=stream_payload, headers=headers) as response:
            if response.is_error:
                await response.aread()
                raise OpenAIUpstreamError(response.status_code, _safe_json(response))
            async for event in _run_stream(response):
                yield event

    async with httpx.AsyncClient(timeout=300.0) as client:
        url, headers, can_refresh = await _build_upstream_request(client)
        upstream_correlation_id = headers.get("X-Correlation-ID")

        if stream_logger:
            stream_logger.info(
                "upstream_connect_start",
                endpoint="/v1/messages/stream",
                upstream_url=url,
                correlation_id=upstream_correlation_id,
            )

        # For OpenAI-like backends, keep LM Studio-specific compatibility fallback behavior.
        if config.require_upstream_mode() == "openai":
            try:
                async for event in _connect_and_stream(client, url, headers, payload):
                    yield event
                return
            except OpenAIUpstreamError as exc:
                # Retry once on Codex refresh (shouldn't happen in openai mode, but keep behavior symmetric).
                if exc.status_code == 401 and can_refresh:
                    await _codex_manager().refresh_on_unauthorized(client)
                    url, headers, _ = await _build_upstream_request(client)
                    async for event in _connect_and_stream(client, url, headers, payload):
                        yield event
                    return

                # LM Studio invalid_union fallback.
                if (
                    exc.status_code == 400
                    and _is_invalid_input_union(exc.error_payload)
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
                        try:
                            async for event in _connect_and_stream(
                                client, url, headers, fallback_payload
                            ):
                                yield event
                            return
                        except OpenAIUpstreamError as exc2:
                            exc = exc2

                    collapsed_payload = collapse_payload(payload)
                    if collapsed_payload != payload and collapsed_payload != fallback_payload:
                        if stream_logger:
                            stream_logger.info(
                                "lmstudio_payload_collapsed",
                                endpoint="/v1/messages/stream",
                                upstream_url=url,
                                correlation_id=upstream_correlation_id,
                            )
                        current_event = None
                        data_lines = []
                        async for event in _connect_and_stream(
                            client, url, headers, collapsed_payload
                        ):
                            yield event
                        return

                raise

        # Codex mode: retry once on 401 after refresh.
        try:
            async for event in _connect_and_stream(client, url, headers, payload):
                yield event
        except OpenAIUpstreamError as exc:
            if exc.status_code == 401 and can_refresh:
                await _codex_manager().refresh_on_unauthorized(client)
                url, headers, _ = await _build_upstream_request(client)
                async for event in _connect_and_stream(client, url, headers, payload):
                    yield event
                return
            raise


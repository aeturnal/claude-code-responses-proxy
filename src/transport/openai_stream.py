"""OpenAI Responses API streaming transport client."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from asgi_correlation_id import correlation_id

from src.codex_auth import (
    CodexAuthManager,
    CodexAuthStore,
    CodexTokenRefreshError,
    MissingCodexCredentialsError,
)
from src import config
from src.observability.logging import get_stream_logger, streaming_logging_enabled
from src.transport.lmstudio import collapse_payload, is_lmstudio_base_url, normalize_payload
from src.transport.openai_client import OpenAIUpstreamError


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


@lru_cache(maxsize=2)
def _codex_manager() -> CodexAuthManager:
    path = (
        Path(config.CODEX_AUTH_PATH).expanduser()
        if config.CODEX_AUTH_PATH
        else Path("~/.codex/auth.json").expanduser()
    )
    return CodexAuthManager(CodexAuthStore(path))


async def _build_upstream_request(
    client: httpx.AsyncClient,
) -> tuple[str, dict[str, str], bool]:
    """Return (url, headers, can_refresh_on_401)."""
    mode = config.require_upstream_mode()
    headers: dict[str, str] = {}

    upstream_correlation_id = correlation_id.get()
    if upstream_correlation_id:
        headers["X-Correlation-ID"] = upstream_correlation_id

    if mode == "openai":
        api_key = config.require_openai_api_key()
        headers["Authorization"] = f"Bearer {api_key}"
        return f"{config.OPENAI_BASE_URL}/responses", headers, False

    try:
        tokens = await _codex_manager().ensure_fresh(client)
    except (MissingCodexCredentialsError, CodexTokenRefreshError) as exc:
        raise config.MissingUpstreamCredentialsError(str(exc) or "Codex credentials missing") from exc

    headers["Authorization"] = f"Bearer {tokens.access_token}"
    if tokens.account_id:
        headers["ChatGPT-Account-ID"] = tokens.account_id
    return f"{config.CODEX_BASE_URL}/responses", headers, True


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

"""OpenAI Responses API transport client."""

from __future__ import annotations

from typing import Any, Dict, Optional

import json

from functools import lru_cache
from pathlib import Path

import httpx
from asgi_correlation_id import correlation_id
import structlog

from src import config
from src.codex_auth import (
    CodexAuthManager,
    CodexAuthStore,
    CodexTokenRefreshError,
    MissingCodexCredentialsError,
)
from src.transport.lmstudio import (
    collapse_payload,
    is_lmstudio_base_url,
    normalize_payload,
)

logger = structlog.get_logger(__name__)


class OpenAIUpstreamError(Exception):
    """Raised when the OpenAI upstream returns an error response."""

    def __init__(self, status_code: int, error_payload: Any) -> None:
        super().__init__(f"OpenAI upstream error ({status_code})")
        self.status_code = status_code
        self.error_payload = error_payload


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"error": {"message": response.text}}


def _codex_rewrite_message_span_types(payload: Dict[str, Any]) -> None:
    input_items = payload.get("input")
    if not isinstance(input_items, list):
        return

    for item in input_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        role = item.get("role")
        if role != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for span in content:
            if not isinstance(span, dict):
                continue
            if span.get("type") == "input_text":
                span["type"] = "output_text"


def _extract_completed_response_from_sse(body: str) -> Optional[Dict[str, Any]]:
    """Parse an OpenAI-style SSE transcript and return the response.completed payload."""
    current_event: Optional[str] = None
    data_lines: list[str] = []

    def _flush() -> Optional[Dict[str, Any]]:
        nonlocal current_event, data_lines
        if current_event is None and not data_lines:
            return None
        event_name = current_event or "message"
        raw = "\n".join(data_lines)
        current_event = None
        data_lines = []
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if event_name == "response.completed" and isinstance(parsed, dict):
            return parsed
        return None

    for line in body.splitlines():
        if line == "":
            result = _flush()
            if result is not None:
                return result
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line[len("event:") :].lstrip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
            continue

    # Flush trailing frame.
    return _flush()


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

    # codex mode
    try:
        tokens = await _codex_manager().ensure_fresh(client)
    except (MissingCodexCredentialsError, CodexTokenRefreshError) as exc:
        raise config.MissingUpstreamCredentialsError(str(exc) or "Codex credentials missing") from exc

    headers["Authorization"] = f"Bearer {tokens.access_token}"
    if tokens.account_id:
        headers["ChatGPT-Account-ID"] = tokens.account_id
    return f"{config.CODEX_BASE_URL}/responses", headers, True


async def create_openai_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST a Responses API payload and return the JSON response."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        url, headers, can_refresh = await _build_upstream_request(client)

        request_payload = dict(payload)
        if config.require_upstream_mode() == "codex":
            # ChatGPT Codex backend requires store=false and stream=true.
            request_payload.setdefault("store", False)
            request_payload.setdefault("stream", True)

            # ChatGPT Codex backend does not accept max_output_tokens/max_tokens.
            request_payload.pop("max_output_tokens", None)
            request_payload.pop("max_tokens", None)

            # ChatGPT Codex backend does not accept max_tool_calls.
            request_payload.pop("max_tool_calls", None)

            # ChatGPT Codex backend expects assistant history content spans to use output_text.
            # (user/system/developer message spans remain input_text)
            _codex_rewrite_message_span_types(request_payload)

        response = await client.post(url, json=request_payload, headers=headers)

        if response.status_code == 401 and can_refresh:
            # Retry once after a forced refresh.
            await _codex_manager().refresh_on_unauthorized(client)
            url, headers, _ = await _build_upstream_request(client)
            response = await client.post(url, json=request_payload, headers=headers)

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            completed = _extract_completed_response_from_sse(response.text)
            if completed is not None:
                return completed

        if response.is_error:
            error_payload = _safe_json(response)
            if response.status_code == 400 and _is_invalid_input_union(error_payload):
                # LM Studio compatibility only applies when using an OpenAI-like base URL.
                if is_lmstudio_base_url() and config.require_upstream_mode() == "openai":
                    fallback_payload = normalize_payload(payload)
                    if fallback_payload != payload:
                        logger.info(
                            "lmstudio_payload_normalized",
                            endpoint="/v1/responses",
                        )
                        response = await client.post(
                            url, json=fallback_payload, headers=headers
                        )
                        if not response.is_error:
                            return response.json()
                        error_payload = _safe_json(response)
                    collapsed_payload = collapse_payload(payload)
                    if (
                        collapsed_payload != payload
                        and collapsed_payload != fallback_payload
                    ):
                        logger.info(
                            "lmstudio_payload_collapsed",
                            endpoint="/v1/responses",
                        )
                        response = await client.post(
                            url, json=collapsed_payload, headers=headers
                        )
                        if not response.is_error:
                            return response.json()
                        error_payload = _safe_json(response)
            raise OpenAIUpstreamError(response.status_code, error_payload)

        return response.json()


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

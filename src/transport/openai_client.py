"""OpenAI Responses API transport client."""

from __future__ import annotations

from typing import Any, Dict, Optional

import json

import httpx
import structlog

from src import config
from src.transport.lmstudio import (
    fallback_payload_candidates,
    is_lmstudio_base_url,
)
from src.transport.upstream_common import (
    build_upstream_request as _build_upstream_request,
    get_codex_manager as _codex_manager,
    is_invalid_input_union as _is_invalid_input_union,
    prepare_codex_payload as _prepare_codex_payload,
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


async def create_openai_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST a Responses API payload and return the JSON response."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        url, headers, can_refresh = await _build_upstream_request(client)

        request_payload = dict(payload)
        if config.require_upstream_mode() == "codex":
            request_payload = _prepare_codex_payload(payload)

        response = await client.post(url, json=request_payload, headers=headers)

        if response.status_code == 401 and can_refresh:
            # Retry once after a forced refresh.
            await _codex_manager().refresh_on_unauthorized(client)
            url, headers, _ = await _build_upstream_request(client)
            response = await client.post(url, json=request_payload, headers=headers)

        # Codex mode forces stream=true. Some upstreams may not reliably set the
        # SSE content-type header, so attempt SSE parse opportunistically.
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type or "event:" in response.text:
            completed = _extract_completed_response_from_sse(response.text)
            if completed is not None:
                return completed

        if response.is_error:
            error_payload = _safe_json(response)
            if response.status_code == 400 and _is_invalid_input_union(error_payload):
                # LM Studio compatibility only applies when using an OpenAI-like base URL.
                if is_lmstudio_base_url() and config.require_upstream_mode() == "openai":
                    for label, fallback_payload in fallback_payload_candidates(payload):
                        logger.info(
                            f"lmstudio_payload_{label}",
                            endpoint="/v1/responses",
                        )
                        response = await client.post(
                            url, json=fallback_payload, headers=headers
                        )
                        if not response.is_error:
                            return response.json()
                        error_payload = _safe_json(response)
            raise OpenAIUpstreamError(response.status_code, error_payload)

        try:
            return response.json()
        except ValueError:
            # Avoid crashing the ASGI app on upstream non-JSON success responses.
            raise OpenAIUpstreamError(
                502,
                {
                    "error": {
                        "message": "Upstream returned non-JSON success response",
                        "upstream_status": response.status_code,
                        "upstream_content_type": content_type,
                    }
                },
            )

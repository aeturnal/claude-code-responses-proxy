"""OpenAI Responses API streaming transport client."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from asgi_correlation_id import correlation_id

from src.config import OPENAI_BASE_URL, require_openai_api_key
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


async def stream_openai_events(
    payload: Dict[str, Any],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream OpenAI Responses API events as parsed SSE frames."""
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

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            if response.is_error:
                await response.aread()
                raise OpenAIUpstreamError(response.status_code, _safe_json(response))

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

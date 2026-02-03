"""OpenAI Responses API transport client."""

from __future__ import annotations

from typing import Any, Dict

import httpx
from asgi_correlation_id import correlation_id
import structlog

from src.config import OPENAI_BASE_URL, require_openai_api_key
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


async def create_openai_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST a Responses API payload and return the JSON response."""
    api_key = require_openai_api_key()
    url = f"{OPENAI_BASE_URL}/responses"
    headers = {"Authorization": f"Bearer {api_key}"}
    upstream_correlation_id = correlation_id.get()
    if upstream_correlation_id:
        headers["X-Correlation-ID"] = upstream_correlation_id

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.is_error:
        error_payload = _safe_json(response)
        if response.status_code == 400 and _is_invalid_input_union(error_payload):
            if is_lmstudio_base_url():
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

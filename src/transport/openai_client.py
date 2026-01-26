"""OpenAI Responses API transport client."""

from __future__ import annotations

from typing import Any, Dict

import httpx

from src.config import OPENAI_BASE_URL, require_openai_api_key


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

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.is_error:
        raise OpenAIUpstreamError(response.status_code, _safe_json(response))

    return response.json()

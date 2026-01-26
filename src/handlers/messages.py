"""/v1/messages handler."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.errors.anthropic_error import build_anthropic_error, map_openai_error_type
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.mapping.openai_to_anthropic import map_openai_response_to_anthropic
from src.schema.anthropic import MessagesRequest
from src.transport.openai_client import OpenAIUpstreamError, create_openai_response

router = APIRouter()


def _extract_openai_error_fields(openai_error: Any) -> Dict[str, Optional[str]]:
    if isinstance(openai_error, dict):
        error_obj = openai_error.get("error")
        if isinstance(error_obj, dict):
            return {
                "message": error_obj.get("message"),
                "param": error_obj.get("param"),
                "code": error_obj.get("code"),
            }
    return {"message": None, "param": None, "code": None}


def _normalize_openai_payload(payload: Any) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    if hasattr(payload, "dict"):
        return payload.dict(exclude_none=True)
    return payload


@router.post("/v1/messages")
async def create_message(request: MessagesRequest) -> Dict[str, Any]:
    """Translate Anthropic Messages request into OpenAI Responses output."""

    openai_request = map_anthropic_request_to_openai(request)
    payload = _normalize_openai_payload(openai_request)
    try:
        response = await create_openai_response(payload)
    except OpenAIUpstreamError as exc:
        error_fields = _extract_openai_error_fields(exc.error_payload)
        error_type = map_openai_error_type(exc.error_payload)
        message = error_fields.get("message") or "OpenAI upstream error"
        error_payload = build_anthropic_error(
            exc.status_code,
            error_type,
            message,
            param=error_fields.get("param"),
            code=error_fields.get("code"),
            openai_error=exc.error_payload,
        )
        return JSONResponse(status_code=exc.status_code, content=error_payload)

    return map_openai_response_to_anthropic(response)

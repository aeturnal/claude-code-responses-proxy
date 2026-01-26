"""/v1/messages/count_tokens handler."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.errors.anthropic_error import build_anthropic_error
from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.schema.anthropic import CountTokensResponse, MessagesRequest
from src.token_counting.openai_count import count_openai_request_tokens

router = APIRouter()


@router.post("/v1/messages/count_tokens", response_model=CountTokensResponse)
async def count_tokens(request: MessagesRequest):
    """Return OpenAI-aligned input token counts for an Anthropic request."""

    try:
        openai_request = map_anthropic_request_to_openai(request)
        input_tokens = count_openai_request_tokens(openai_request)
    except ValueError as exc:
        error_payload = build_anthropic_error(
            400,
            "invalid_request_error",
            str(exc) or "Invalid request",
        )
        return JSONResponse(status_code=400, content=error_payload)

    return CountTokensResponse(input_tokens=input_tokens)

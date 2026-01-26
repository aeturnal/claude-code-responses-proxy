"""FastAPI application wiring."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.errors.anthropic_error import build_anthropic_error
from src.handlers.count_tokens import router as count_tokens_router
from src.handlers.messages import router as messages_router

app = FastAPI()


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    error_payload = build_anthropic_error(
        400,
        "invalid_request_error",
        "Invalid request",
        openai_error={"errors": exc.errors()},
    )
    return JSONResponse(status_code=400, content=error_payload)


app.include_router(messages_router)
app.include_router(count_tokens_router)

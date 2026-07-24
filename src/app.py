"""FastAPI application wiring."""

from __future__ import annotations

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.errors.anthropic_error import build_anthropic_error
from src.handlers.anthropic_telemetry import router as anthropic_telemetry_router
from src.handlers.count_tokens import router as count_tokens_router
from src.handlers.messages import router as messages_router
from src.middleware.observability import ObservabilityMiddleware
from src.observability.logging import configure_logging, logging_enabled

app = FastAPI()
logger = structlog.get_logger(__name__)
configure_logging()
app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-ID")
app.add_middleware(ObservabilityMiddleware)


def summarize_validation_errors(
    errors: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid request"),
            "type": error.get("type", "value_error"),
        }
        for error in errors
    ]


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = summarize_validation_errors(exc.errors())
    if logging_enabled():
        logger.info("request_validation_error", errors=details)
    error_payload = build_anthropic_error(
        400,
        "invalid_request_error",
        "Invalid request",
        openai_error={"errors": details},
    )
    return JSONResponse(status_code=400, content=error_payload)


app.include_router(messages_router)
app.include_router(count_tokens_router)
app.include_router(anthropic_telemetry_router)

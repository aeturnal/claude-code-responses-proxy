"""Observability middleware for request context binding."""

from __future__ import annotations

import time

from asgi_correlation_id import correlation_id
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        clear_contextvars()
        request.state.start_time = time.perf_counter()

        request_correlation_id = correlation_id.get()
        request.state.correlation_id = request_correlation_id
        if request_correlation_id:
            bind_contextvars(correlation_id=request_correlation_id)

        try:
            response = await call_next(request)
            return response
        finally:
            clear_contextvars()

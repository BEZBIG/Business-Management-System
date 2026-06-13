"""
Request ID (correlation-id) middleware (D-11).

For every incoming request:
  - Reads the X-Request-ID header if the caller provides one (useful for tracing
    across service boundaries).
  - Generates a fresh UUID4 hex string if the header is absent.
  - Binds the request_id to the structlog context-vars so that every log line
    emitted during the request automatically carries the field.
  - Propagates the request_id back to the caller via X-Request-ID response header.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injects a per-request correlation ID into every structlog log entry."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next: object) -> Response:
        # Use caller-supplied ID or generate a new one
        request_id: str = request.headers.get(self._header_name) or uuid.uuid4().hex

        # Clear any leftovers from a previous request on this thread/task
        structlog.contextvars.clear_contextvars()
        # Bind to structlog context — picked up by merge_contextvars processor
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response: Response = await call_next(request)  # type: ignore[arg-type]

        # Echo the ID back so callers can correlate logs
        response.headers[self._header_name] = request_id
        return response

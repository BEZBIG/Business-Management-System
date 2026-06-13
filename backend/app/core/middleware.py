"""Middleware, проставляющий request_id (correlation-id) для трассировки запросов."""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Привязывает correlation-id к каждой записи лога structlog для текущего запроса."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next: object) -> Response:
        request_id: str = request.headers.get(self._header_name) or uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response: Response = await call_next(request)  # type: ignore[operator]

        response.headers[self._header_name] = request_id
        return response

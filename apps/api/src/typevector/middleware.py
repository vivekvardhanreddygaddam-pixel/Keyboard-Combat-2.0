"""TypeVector Arena — Request ID and Context Middleware."""

import contextvars
import uuid
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable holding the active request ID for the current async task
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="system-init"
)


def get_current_request_id() -> str:
    """Return the active request ID or default to system-init."""
    return request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates an X-Request-ID header on every HTTP request."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        # Check incoming header or generate a fresh UUID4
        incoming_id = request.headers.get("X-Request-ID")
        req_id = incoming_id if incoming_id and len(incoming_id) <= 64 else str(uuid.uuid4())

        # Store in context variable for the duration of this request
        token = request_id_ctx.set(req_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)

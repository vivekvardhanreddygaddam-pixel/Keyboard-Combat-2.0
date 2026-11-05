"""TypeVector Arena — Background Worker Task Correlation and Privacy-Aware Structured Logging.

Guarantees:
1. Every task execution is tagged with a traceable correlation/request ID.
2. Private typing input, passwords, session tokens, and secrets are NEVER logged.
"""

import contextvars
import logging
import time
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger("typevector.workers")

# Context variable preserving correlation ID across async and worker calls
_current_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_correlation_id", default=None
)

# Sensitive keys to scrub from task arguments before structured logging
SENSITIVE_ARG_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "token",
        "session_token",
        "keystrokes",
        "input_text",
        "content",
        "prompt_content",
        "api_key",
        "csrf_token",
        "headers",
    }
)


def get_correlation_id() -> str:
    """Return the active correlation ID or generate a new UUID4 string."""
    cid = _current_correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())
        _current_correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the active correlation ID for the current context."""
    _current_correlation_id.set(cid)


def sanitize_payload(payload: Any) -> Any:  # noqa: ANN401
    """Recursively scrub sensitive keys and long arrays from logged payloads."""
    if isinstance(payload, dict):
        clean: dict[str, Any] = {}
        for k, v in payload.items():
            if str(k).lower() in SENSITIVE_ARG_KEYS:
                clean[k] = "[REDACTED]"
            else:
                clean[k] = sanitize_payload(v)
        return clean
    if isinstance(payload, list):
        if len(payload) > 10:
            return f"[Array of {len(payload)} items]"
        return [sanitize_payload(item) for item in payload]
    if isinstance(payload, str) and len(payload) > 200:
        return f"{payload[:30]}... [truncated {len(payload)} chars]"
    return payload


def task_logging_wrapper(task_name: str) -> Callable[..., Any]:
    """Decorator for Celery task functions adding structured logging and correlation tracking."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            correlation_id = kwargs.pop("correlation_id", None) or get_correlation_id()
            set_correlation_id(correlation_id)

            safe_kwargs = sanitize_payload(kwargs)
            logger.info(
                "Task '%s' started [correlation_id=%s] args_count=%d kwargs=%s",
                task_name,
                correlation_id,
                len(args),
                safe_kwargs,
            )
            start_time = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                elapsed_ms = (time.monotonic() - start_time) * 1000
                logger.info(
                    "Task '%s' completed successfully [correlation_id=%s] duration=%.2fms",
                    task_name,
                    correlation_id,
                    elapsed_ms,
                )
                return result
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                logger.error(
                    "Task '%s' failed [correlation_id=%s] duration=%.2fms error=%s",
                    task_name,
                    correlation_id,
                    elapsed_ms,
                    exc,
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator

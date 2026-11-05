"""TypeVector Arena — Structured Logging Configuration."""

import logging
import sys
from typing import Any

from typevector.config import settings


class StructuredFormatter(logging.Formatter):
    """Formats log records as structured text or JSON-like log entries."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        record_dict: dict[str, Any] = {
            "timestamp": f"{timestamp}.{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include request_id if present in record attributes
        request_id = getattr(record, "request_id", None)
        if request_id:
            record_dict["request_id"] = request_id

        if record.exc_info:
            record_dict["exception"] = self.formatException(record.exc_info)

        # In production, render single-line JSON or formatted text
        if settings.is_production:
            import json

            return json.dumps(record_dict, default=str)

        # In development, readable structured format
        req_part = f" [{request_id}]" if request_id else ""
        exc_part = f"\n{record_dict['exception']}" if "exception" in record_dict else ""
        return f"{record_dict['timestamp']} [{record.levelname:<8}] {record.name}{req_part}: {record.getMessage()}{exc_part}"


def setup_logging() -> None:
    """Initialize structured logging for TypeVector Arena."""
    log_level = logging.DEBUG if settings.app_debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet overly chatty loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


logger = logging.getLogger("typevector")


def get_logger(name: str) -> logging.Logger:
    """Return a logger instance with the given name."""
    return logging.getLogger(name)

import json
import logging
import sys
import contextvars
from datetime import datetime, timezone
from typing import Any

from core.config import settings


# Context variable to hold the request_id for the current request context
request_id_ctx_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


class RequestIDFilter(logging.Filter):
    """A logging filter to inject the request_id from a ContextVar into LogRecord."""
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_ctx_var.get()
        if request_id:
            record.request_id = request_id  # Attach request_id to the log record
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "environment": settings.ENV,
            "project": settings.PROJECT_NAME,
        }

        # Include exception traceback if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Extract any extra fields provided during logging or by filters (like request_id)
        standard_record_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "request_id" # Add request_id here to prevent it from being picked up twice if set explicitly
        }
        for key, value in record.__dict__.items():
            if key not in standard_record_attrs and not key.startswith("_"):
                log_data[key] = value

        # Explicitly add request_id if it exists on the record, after other extra attributes
        # This ensures it's always at the top level of the JSON output.
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        return json.dumps(log_data)


def get_logger(name: str) -> logging.Logger:
    """
    Configure and return a standard logger instance formatted with JSON logs.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Prevent duplicate handlers if logger is fetched multiple times
    if not logger.handlers:
        # Add the RequestIDFilter to the logger
        logger.addFilter(RequestIDFilter())

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger

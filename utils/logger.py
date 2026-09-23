import json
import logging
import sys
import contextvars
from datetime import datetime, timezone
from typing import Any

from core.config import settings


# Context variable to hold the request_id for the current request context
request_id_ctx_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


# Removed RequestIDFilter as its logic is now handled by JSONFormatter directly


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

        # --- BEGIN: Specific handling for request_id ---
        # Prioritize request_id from context variable
        request_id_from_ctx = request_id_ctx_var.get()
        if request_id_from_ctx:
            log_data["request_id"] = request_id_from_ctx
        # Fallback: check if request_id was passed via `extra` or manually set on the record
        elif hasattr(record, "request_id") and record.request_id is not None:
            log_data["request_id"] = record.request_id
        else:
            log_data["request_id"] = None # Ensure it's explicitly None if not found
        # --- END: Specific handling for request_id ---


        # Extract any other custom extra fields provided during logging
        # `request_id` is now explicitly handled, so ensure it's listed in standard_record_attrs
        # so it's not duplicated if present in record.__dict__ (e.g., from `extra`)
        standard_record_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process",
            "request_id" # Explicitly list request_id to prevent it being added again from record.__dict__
        }
        for key, value in record.__dict__.items():
            if key not in standard_record_attrs and not key.startswith("_") and not callable(value):
                log_data[key] = value

        return json.dumps(log_data)


def get_logger(name: str) -> logging.Logger:
    """
    Configure and return a standard logger instance formatted with JSON logs.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Prevent duplicate handlers if logger is fetched multiple times
    if not logger.handlers:
        # Removed RequestIDFilter as its functionality is now handled by JSONFormatter directly
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger
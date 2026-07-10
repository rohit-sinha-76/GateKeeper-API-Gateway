import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from core.config import settings


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

        # Extract any extra fields provided during logging
        standard_record_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process"
        }
        for key, value in record.__dict__.items():
            if key not in standard_record_attrs and not key.startswith("_"):
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
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger

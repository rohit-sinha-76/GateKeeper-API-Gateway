import json
import logging
from utils.logger import JSONFormatter, get_logger


def test_json_formatter_outputs_valid_json():
    """Verify JSONFormatter produces parseable JSON with required metadata fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test event message",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-abc-999"
    record.status_code = 200

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["message"] == "Test event message"
    assert data["logger"] == "test_logger"
    assert data["request_id"] == "req-abc-999"
    assert data["status_code"] == 200
    assert "timestamp" in data


def test_get_logger_singleton():
    """Verify get_logger returns initialized logger without duplicate handlers."""
    logger1 = get_logger("my_service")
    logger2 = get_logger("my_service")
    assert logger1 is logger2
    assert len(logger1.handlers) == 1

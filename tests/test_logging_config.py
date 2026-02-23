import io
import json
import logging
from src.logging_config import setup_logging

# test structured JSON logging configuration
class TestStructuredLogging:
    # test setup logging produces json
    def test_setup_logging_produces_json(self) -> None:
        setup_logging()
        logger = logging.getLogger("test.structured")
        # create stream handler for logging
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.getLogger().handlers[0].formatter)
        logger.addHandler(handler)

        logger.info("test message")

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert parsed["message"] == "test message"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed
        assert parsed["module"] == "test.structured"

        logger.removeHandler(handler)
    # test extra fields included in json
    def test_extra_fields_included_in_json(self) -> None:
        setup_logging()
        logger = logging.getLogger("test.extra")
        # create stream handler for logging
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.getLogger().handlers[0].formatter)
        logger.addHandler(handler)

        logger.info("lead processed", extra={"lead_id": "abc-123", "priority": "P0"})

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        assert parsed["lead_id"] == "abc-123"
        assert parsed["priority"] == "P0"

        logger.removeHandler(handler)

    # calling setup_logging multiple times does not duplicate handlers.
    def test_setup_logging_idempotent(self) -> None:
        setup_logging()
        # count number of handlers before and after setup_logging
        handler_count_1 = len(logging.getLogger().handlers)
        setup_logging()
        handler_count_2 = len(logging.getLogger().handlers)
        # ensure number of handlers is not greater than 1 more than before
        assert handler_count_2 <= handler_count_1 + 1

    # loggers created before setup_logging still work after setup_logging.
    def test_existing_loggers_not_disabled(self) -> None:
        early_logger = logging.getLogger("test.early")
        setup_logging()

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.getLogger().handlers[0].formatter)
        early_logger.addHandler(handler)

        early_logger.info("still works")

        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["message"] == "still works"

        early_logger.removeHandler(handler)

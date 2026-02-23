import logging
import logging.config

# configure structured JSON logging for the entire application
def setup_logging(log_level: str = "INFO") -> None:
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "rename_fields": {
                    "asctime": "timestamp",
                    "levelname": "level",
                    "name": "module",
                },
                "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            }
        },
        "filters": {
            "request_id": {
                "()": "src.api.middleware.RequestIdFilter",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
                "filters": ["request_id"],
            }
        },
        "root": {
            "level": log_level,
            "handlers": ["console"],
        },
    }
    logging.config.dictConfig(config)

import logging
from typing import Any

import structlog
from structlog.stdlib import BoundLogger
from structlog.typing import EventDict

from .runtime import AppSettings


def add_correlation_id(_logger: object, _method: str, event: EventDict) -> EventDict:
    correlation_id = structlog.contextvars.get_contextvars().get("correlation_id")
    if correlation_id is not None:
        event["correlation_id"] = correlation_id
    return event


def django_logging(level: str) -> dict[str, Any]:
    """Route structured events and suppress raw HTTP diagnostics."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
            "discard": {"class": "logging.NullHandler"},
        },
        "loggers": {
            "cms": {"handlers": ["stdout"], "level": level, "propagate": False},
            # Completion events are required at every application log level.
            "cms.http": {"level": "INFO", "propagate": True},
            # Django's raw request diagnostics can contain paths, cookies and exception text.
            **{
                name: {"handlers": ["discard"], "level": logging.CRITICAL + 1, "propagate": False}
                for name in ("django.request", "django.server", "django.security", "django.channels.server")
            },
        },
    }


def configure_logging(settings: AppSettings) -> BoundLogger:
    """Bind the application event fields once during Django bootstrap."""
    structlog.configure(
        processors=[
            add_correlation_id,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=BoundLogger,
    )
    return structlog.stdlib.get_logger("cms").bind(
        component="cms-api", environment=settings.environment, release=settings.release or "local"
    )

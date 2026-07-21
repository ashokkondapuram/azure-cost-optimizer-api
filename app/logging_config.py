"""Central logging setup — stdlib + structlog at LOG_LEVEL (default INFO)."""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, level: str = "INFO", json_logs: bool = False) -> str:
    """
    Configure application logging once at startup.

    Returns the resolved level name (e.g. INFO).
    """
    level_name = (level or "INFO").strip().upper()
    level_num = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level_num,
        force=True,
    )

    # Keep third-party noise down unless debugging.
    noisy = ("azure", "urllib3", "httpx", "httpcore", "sqlalchemy.engine", "uvicorn.access")
    for name in noisy:
        logging.getLogger(name).setLevel(
            logging.WARNING if level_num > logging.DEBUG else logging.DEBUG,
        )

    logging.getLogger("app").setLevel(level_num)

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level_num)

    logging.getLogger(__name__).info("Logging configured at %s", level_name)
    return level_name


def get_logger(name: str | None = None):
    """Return a structlog logger (supports keyword context fields like error=, count=)."""
    return structlog.get_logger(name)

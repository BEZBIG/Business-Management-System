"""
Structured JSON logging via structlog (D-11).

Call setup_logging() once at application startup (e.g., in main.py or lifespan).
After that, obtain a logger with structlog.get_logger() — all log entries are
emitted as JSON with fields: timestamp, level, logger, request_id (injected by
RequestIDMiddleware via structlog.contextvars).
"""

import logging

import structlog


def setup_logging() -> None:
    """Configure structlog to emit JSON logs to stdout.

    Processor chain:
      1. merge_contextvars  — pulls request_id (and any other bound vars) into every event
      2. add_log_level      — adds the "level" key
      3. add_logger_name    — adds the "logger" key
      4. TimeStamper        — adds ISO-8601 "timestamp" key
      5. StackInfoRenderer  — renders stack_info argument (if provided)
      6. format_exc_info    — renders exception tracebacks as strings
      7. JSONRenderer       — serialises the event dict to a JSON string (D-11)
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Route stdlib logging through structlog so third-party libs also emit JSON
    logging.basicConfig(format="%(message)s", level=logging.INFO)

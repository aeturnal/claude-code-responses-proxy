"""Structured logging configuration for observability."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog

from src.config import OBS_LOG_ENABLED, OBS_LOG_FILE, OBS_LOG_PRETTY


def logging_enabled() -> bool:
    return OBS_LOG_ENABLED


def _build_renderer() -> structlog.processors.JSONRenderer:
    if OBS_LOG_PRETTY:
        return structlog.processors.JSONRenderer(indent=2, sort_keys=True)
    return structlog.processors.JSONRenderer()


def _configure_stdlib_logging() -> None:
    renderer = _build_renderer()
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=pre_chain,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    file_path = Path(OBS_LOG_FILE)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    root_logger.addHandler(file_handler)


def configure_logging() -> None:
    if not logging_enabled():
        return

    _configure_stdlib_logging()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            _build_renderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

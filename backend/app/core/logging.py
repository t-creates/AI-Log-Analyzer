# app/core/logging.py
"""
Application-wide logging configuration.

Purpose:
- Centralize logging setup (DRY)
- Provide consistent, structured log output
- Make it easy to increase verbosity in dev without code changes

This module is intentionally lightweight.
If we later need JSON logs, tracing, or external log shipping,
we can extend this without touching application logic.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """
    Configure root logging for the application.

    Args:
        level: Logging level as a string (e.g. "INFO", "DEBUG", "WARNING").

    Behavior:
    - Sets a single stream handler to stdout (container-friendly)
    - Applies a consistent, readable log format
    - Safe to call once during application startup
    """

    # Convert level string to logging constant safely
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Clear any existing handlers to avoid duplicate logs
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

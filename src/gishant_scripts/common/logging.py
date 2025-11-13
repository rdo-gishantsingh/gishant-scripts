"""Logging utilities for gishant scripts."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(
    name: str,
    level: str | int = "INFO",
    log_file: Path | None = None,
    console: bool = True,
) -> logging.Logger:
    """Setup standardized logging configuration.

    Args:
        name: Logger name (usually __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) or logging constant
        log_file: Optional file path to write logs
        console: Whether to also log to console (default: True)

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logging(__name__, level="DEBUG")
        >>> logger.info("Script started")
    """
    logger = logging.getLogger(name)
    if isinstance(level, str):
        logger.setLevel(getattr(logging, level.upper()))
    else:
        logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

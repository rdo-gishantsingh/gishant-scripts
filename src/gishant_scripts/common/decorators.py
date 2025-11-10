"""Reusable decorators for gishant scripts."""

import functools
import logging
import time
from collections.abc import Callable
from typing import Any


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 1.0)
        backoff: Multiplier for delay after each attempt (default: 2.0)

    Example:
        >>> @retry(max_attempts=3, delay=1.0, backoff=2.0)
        ... def fetch_data():
        ...     return api_call()
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            logger = logging.getLogger(func.__module__)

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as err:
                    if attempt == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {err}")
                        raise

                    logger.warning(f"Attempt {attempt}/{max_attempts} failed: {err}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff

        return wrapper

    return decorator


def timing(func: Callable) -> Callable:
    """Decorator to measure and log function execution time.

    Example:
        >>> @timing
        ... def process_data(items):
        ...     return [process(item) for item in items]
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        logger = logging.getLogger(func.__module__)
        start = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start
            logger.info(f"{func.__name__} took {duration:.2f}s")

    return wrapper

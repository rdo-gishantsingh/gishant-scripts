"""Tests for core.decorators module."""

import logging
import time

import pytest

from gishant_scripts.common.decorators import retry, timing


class TestRetryDecorator:
    """Test @retry decorator."""

    def test_retry_success_first_attempt(self):
        """Test function succeeds on first attempt."""
        call_count = 0

        @retry(max_attempts=3)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()
        assert result == "success"
        assert call_count == 1

    def test_retry_success_after_failures(self):
        """Test function succeeds after some failures."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausts_attempts(self):
        """Test function fails after max attempts."""

        @retry(max_attempts=3, delay=0.01)
        def always_fails():
            raise ValueError("Persistent error")

        with pytest.raises(ValueError) as exc_info:
            always_fails()
        assert str(exc_info.value) == "Persistent error"

    def test_retry_with_backoff(self):
        """Test exponential backoff timing."""
        timestamps = []

        @retry(max_attempts=3, delay=0.1, backoff=2)
        def timed_function():
            timestamps.append(time.time())
            raise ValueError("Error")

        with pytest.raises(ValueError):
            timed_function()

        assert len(timestamps) == 3
        # Check delays: ~0.1s, ~0.2s
        delay1 = timestamps[1] - timestamps[0]
        delay2 = timestamps[2] - timestamps[1]
        assert 0.08 < delay1 < 0.15  # ~0.1s with tolerance
        assert 0.18 < delay2 < 0.25  # ~0.2s with tolerance

    def test_retry_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""

        @retry()
        def documented_function():
            """This is a documented function."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."

    def test_retry_with_args_kwargs(self):
        """Test decorator works with function arguments."""

        @retry(max_attempts=2, delay=0.01)
        def function_with_args(a, b, c=3):
            if a < 2:
                raise ValueError("a too small")
            return a + b + c

        with pytest.raises(ValueError):
            function_with_args(1, 2)

        result = function_with_args(2, 3, c=4)
        assert result == 9


class TestTimingDecorator:
    """Test @timing decorator."""

    def test_timing_measures_duration(self, caplog):
        """Test timing decorator measures execution time."""

        @timing
        def timed_function():
            time.sleep(0.1)
            return "done"

        with caplog.at_level(logging.INFO):
            result = timed_function()
            output = caplog.text

        assert result == "done"
        assert "timed_function" in output
        assert "took" in output
        assert "0." in output  # Check for decimal time like '0.10s'

    def test_timing_with_fast_function(self, caplog):
        """Test timing with very fast function."""

        @timing
        def fast_function():
            return "quick"

        with caplog.at_level(logging.INFO):
            result = fast_function()
            output = caplog.text

        assert result == "quick"
        assert "fast_function" in output
        assert "took" in output

    def test_timing_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""

        @timing
        def documented_function():
            """This is a timed function."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a timed function."

    def test_timing_with_args_kwargs(self, caplog):
        """Test decorator works with function arguments."""

        @timing
        def function_with_args(a, b, c=3):
            return a + b + c

        with caplog.at_level(logging.INFO):
            result = function_with_args(1, 2, c=4)
            output = caplog.text

        assert result == 7
        assert "function_with_args" in output
        assert "took" in output

    def test_timing_with_exception(self, caplog):
        """Test timing decorator still measures time on exception."""

        @timing
        def failing_function():
            time.sleep(0.05)
            raise ValueError("Test error")

        with caplog.at_level(logging.INFO):
            with pytest.raises(ValueError):
                failing_function()
            output = caplog.text

        assert "failing_function" in output
        assert "took" in output

    def test_combined_decorators(self, caplog):
        """Test @retry and @timing can be combined."""
        call_count = 0

        @timing
        @retry(max_attempts=3, delay=0.01)
        def combined_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Retry me")
            return "success"

        with caplog.at_level(logging.INFO):
            result = combined_function()
            output = caplog.text

        assert result == "success"
        assert call_count == 2
        assert "combined_function" in output
        assert "took" in output

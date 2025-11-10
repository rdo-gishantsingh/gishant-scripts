"""Test configuration for gishant-scripts."""

import pytest


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return {"test_key": "test_value"}

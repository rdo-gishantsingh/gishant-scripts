"""Tests for the sandbox backend base layer."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.base import (
    Backend,
    BackendUnavailable,
    Environment,
)


def test_environment_values_and_is_test() -> None:
    assert Environment.TEST.value == "test"
    assert Environment.PRODUCTION.value == "production"
    assert Environment.TEST.is_test
    assert not Environment.PRODUCTION.is_test


class _Dummy(Backend):
    @property
    def project_name(self) -> str:
        return self._raw_project_name


def test_backend_defaults_to_test_env() -> None:
    backend = _Dummy("MyProj")
    assert backend._environment is Environment.TEST
    assert backend.project_name == "MyProj"


def test_backend_unavailable_is_exception() -> None:
    with pytest.raises(BackendUnavailable):
        raise BackendUnavailable("nope")

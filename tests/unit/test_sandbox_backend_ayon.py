"""Tests for AyonBackend credential and name resolution."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.ayon import AyonBackend
from gishant_scripts.sandbox.backends.base import BackendUnavailableError, Environment
from gishant_scripts.sandbox.config import ProjectConfig

_CFG = ProjectConfig(
    canonical_key="DEMO",
    shotgrid="DEMO_SG",
    kitsu="Demo Kitsu",
    ayon="Demo_Ayon",
    storage="Demo_Store",
)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gishant_scripts.sandbox.backends.ayon.load_rdo_env", lambda: None)


def test_project_name_uses_config() -> None:
    assert AyonBackend("DEMO", project_config=_CFG).project_name == "Demo_Ayon"


def test_project_name_falls_back_to_raw() -> None:
    assert AyonBackend("DEMO").project_name == "DEMO"


def test_credentials_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AYON_TEST_SERVER_URL", "https://test.ayon")
    monkeypatch.setenv("AYON_TEST_API_KEY", "key-test")
    backend = AyonBackend("DEMO", environment=Environment.TEST)
    assert backend.credentials() == ("https://test.ayon", "key-test")


def test_credentials_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AYON_SERVER_URL", "https://prod.ayon")
    monkeypatch.setenv("AYON_API_KEY", "key-prod")
    backend = AyonBackend("DEMO", environment=Environment.PRODUCTION)
    assert backend.credentials() == ("https://prod.ayon", "key-prod")


def test_connect_raises_when_creds_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AYON_TEST_SERVER_URL", raising=False)
    monkeypatch.delenv("AYON_TEST_API_KEY", raising=False)
    with pytest.raises(BackendUnavailableError, match="AYON_TEST_"):
        AyonBackend("DEMO", environment=Environment.TEST).connect()

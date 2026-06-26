"""Tests for KitsuBackend credential and name resolution."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.base import BackendUnavailableError, Environment
from gishant_scripts.sandbox.backends.kitsu import KitsuBackend
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
    monkeypatch.setattr("gishant_scripts.sandbox.backends.kitsu.load_rdo_env", lambda: None)


def test_project_name_uses_config() -> None:
    assert KitsuBackend("DEMO", project_config=_CFG).project_name == "Demo Kitsu"


def test_project_name_falls_back_to_raw() -> None:
    assert KitsuBackend("DEMO").project_name == "DEMO"


def test_credentials_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDO_KITSU_TEST_HOST", "https://test.kitsu")
    monkeypatch.setenv("RDO_KITSU_TEST_API_TOKEN", "tok-test")
    monkeypatch.setenv("RDO_KITSU_HOST", "https://prod.kitsu")
    backend = KitsuBackend("DEMO", environment=Environment.TEST)
    assert backend.credentials() == ("https://test.kitsu", "tok-test")


def test_credentials_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDO_KITSU_HOST", "https://prod.kitsu")
    monkeypatch.setenv("RDO_KITSU_API_TOKEN", "tok-prod")
    backend = KitsuBackend("DEMO", environment=Environment.PRODUCTION)
    assert backend.credentials() == ("https://prod.kitsu", "tok-prod")


def test_connect_raises_when_creds_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RDO_KITSU_TEST_HOST", raising=False)
    monkeypatch.delenv("RDO_KITSU_TEST_API_TOKEN", raising=False)
    with pytest.raises(BackendUnavailableError, match="RDO_KITSU_TEST_"):
        KitsuBackend("DEMO", environment=Environment.TEST).connect()

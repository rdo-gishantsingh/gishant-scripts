"""Tests for ShotGridBackend credential and name resolution."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.base import BackendUnavailableError, Environment
from gishant_scripts.sandbox.backends.shotgrid import ShotGridBackend
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
    monkeypatch.setattr("gishant_scripts.sandbox.backends.shotgrid.load_rdo_env", lambda: None)


def test_project_name_uses_config() -> None:
    assert ShotGridBackend("DEMO", project_config=_CFG).project_name == "DEMO_SG"


def test_project_name_falls_back_to_raw() -> None:
    assert ShotGridBackend("DEMO").project_name == "DEMO"


def test_credentials_same_for_both_envs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOTGRID_SERVER_URL", "https://sg")
    monkeypatch.setenv("SHOTGRID_SCRIPT", "script")
    monkeypatch.setenv("SHOTGRID_API_KEY", "key")
    for env in (Environment.TEST, Environment.PRODUCTION):
        backend = ShotGridBackend("DEMO", environment=env)
        assert backend.credentials() == ("https://sg", "script", "key")


def test_connect_raises_when_creds_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOTGRID_SERVER_URL", raising=False)
    monkeypatch.delenv("SHOTGRID_SCRIPT", raising=False)
    monkeypatch.delenv("SHOTGRID_API_KEY", raising=False)
    with pytest.raises(BackendUnavailableError, match="SHOTGRID_"):
        ShotGridBackend("DEMO").connect()

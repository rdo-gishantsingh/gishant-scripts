"""Smoke tests that verify CLI subcommands expose --help without errors."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from gishant_scripts.cli import app

runner = CliRunner()


def test_main_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "cmd",
    ["youtrack", "github", "media", "bookstack", "task-workspace", "testdata"],
)
def test_subcommand_help(cmd: str) -> None:
    result = runner.invoke(app, [cmd, "--help"])
    assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


@pytest.mark.parametrize(
    "cmd",
    ["generate", "cleanup"],
)
def test_testdata_nested_help(cmd: str) -> None:
    result = runner.invoke(app, ["testdata", cmd, "--help"])
    assert result.exit_code == 0, f"testdata {cmd} --help failed: {result.output}"
    assert "--sequence" in result.output
    assert "--shot" in result.output
    assert "Examples:" in result.output

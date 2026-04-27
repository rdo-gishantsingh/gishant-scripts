"""Project name configuration for multi-backend testdata operations."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_PROJECTS_TOML = Path(__file__).parent / "projects.toml"


@dataclass(frozen=True)
class ProjectConfig:
    """Per-backend project name mapping for a canonical project key."""

    canonical_key: str
    shotgrid: str
    kitsu: str
    ayon: str
    storage: str


def load_projects(path: Path | None = None) -> dict[str, ProjectConfig]:
    """Load project name mappings from a TOML file.

    Returns a dict keyed by canonical project key (e.g. "BARBIE_NUTCRACKER").
    """
    config_path = path or _DEFAULT_PROJECTS_TOML
    with config_path.open("rb") as f:
        data = tomllib.load(f)

    return {
        key: ProjectConfig(
            canonical_key=key,
            shotgrid=values["shotgrid"],
            kitsu=values["kitsu"],
            ayon=values["ayon"],
            storage=values.get("storage", values["shotgrid"]),
        )
        for key, values in data.get("projects", {}).items()
    }


def resolve_project(canonical_key: str, path: Path | None = None) -> ProjectConfig:
    """Return the ProjectConfig for a canonical key, or raise KeyError."""
    projects = load_projects(path)
    if canonical_key not in projects:
        available = ", ".join(sorted(projects))
        msg = f"Unknown project key '{canonical_key}'. Available: {available}"
        raise KeyError(msg)
    return projects[canonical_key]


def allowed_project_keys(path: Path | None = None) -> frozenset[str]:
    """Return the set of allowed canonical project keys from the config file."""
    return frozenset(load_projects(path))

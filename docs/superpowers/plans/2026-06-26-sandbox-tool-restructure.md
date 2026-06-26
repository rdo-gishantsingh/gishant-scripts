# Sandbox Tool Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the `testdata` VFX data tool into a cleaner `sandbox` package with two commands (`generate`, `cleanup`), folding whole-project removal into `cleanup` and extracting a per-backend connection layer.

**Architecture:** A `backends/` layer holds one small class per backend (Kitsu, ShotGrid, AYON, Storage) owning credentials, connection, and per-backend project-name resolution. Two orchestrators (`EpisodeGenerator`, `FolderCleanup`) plus a new `ProjectRemoval` orchestrator use that layer; CLI exposes `generate` and a two-mode `cleanup`. Built alongside the old package, then `testdata` is deleted.

**Tech Stack:** Python 3.11+, Typer, Rich, python-dotenv, pytest. Optional runtime libs: `gazu` (Kitsu), `shotgun_api3` (ShotGrid), `ayon_api` (AYON) — all imported lazily and guarded.

## Global Constraints

- **NO LIVE EXECUTION.** Every test mocks all backends. Never connect to or delete from any real Kitsu / ShotGrid / AYON / NAS — test or production. Verification is limited to `pytest` on mocked code and `--help` / argument-parsing smoke checks. Never invoke `generate` or `cleanup` against real servers.
- Match existing repo style: `from __future__ import annotations`, module-level `_log = logging.getLogger(__name__)`, lazy backend imports guarded for `ImportError`, Rich `Console` for user output, Google-style docstrings.
- Credentials always loaded from `~/.rdo/.env` via `python-dotenv`.
- Env var names (verbatim): Kitsu test `RDO_KITSU_TEST_HOST` / `RDO_KITSU_TEST_API_TOKEN`, prod `RDO_KITSU_HOST` / `RDO_KITSU_API_TOKEN`; AYON test `AYON_TEST_SERVER_URL` / `AYON_TEST_API_KEY`, prod `AYON_SERVER_URL` / `AYON_API_KEY`; ShotGrid (no env split) `SHOTGRID_SERVER_URL` / `SHOTGRID_SCRIPT` / `SHOTGRID_API_KEY`.
- Run tests with `uv run pytest` (repo uses `uv`).
- Commit after each task.

---

### Task 1: Scaffold `sandbox` package — port unchanged modules

**Files:**
- Create: `src/gishant_scripts/sandbox/__init__.py`
- Create: `src/gishant_scripts/sandbox/config.py` (copy of `testdata/config.py`)
- Create: `src/gishant_scripts/sandbox/projects.toml` (copy of `testdata/projects.toml`)
- Create: `src/gishant_scripts/sandbox/selection.py` (copy of `testdata/selection.py`)
- Test: `tests/unit/test_sandbox_config.py`
- Test: `tests/unit/test_sandbox_selection.py`

**Interfaces:**
- Produces: `gishant_scripts.sandbox.config` with `ProjectConfig` (frozen dataclass: `canonical_key`, `shotgrid`, `kitsu`, `ayon`, `storage`), `load_projects(path=None) -> dict[str, ProjectConfig]`, `resolve_project(canonical_key, path=None) -> ProjectConfig`, `allowed_project_keys(path=None) -> frozenset[str]`.
- Produces: `gishant_scripts.sandbox.selection.SelectionScope` (frozen dataclass, fields `sequence_patterns`, `shot_patterns`; properties `is_episode_scope`, `is_sequence_scope`, `is_shot_scope`; methods `matches_sequence(name)`, `matches_shot(seq, shot)`).

- [ ] **Step 1: Copy the three unchanged modules and the package docstring**

```bash
mkdir -p src/gishant_scripts/sandbox
cp src/gishant_scripts/testdata/config.py     src/gishant_scripts/sandbox/config.py
cp src/gishant_scripts/testdata/projects.toml src/gishant_scripts/sandbox/projects.toml
cp src/gishant_scripts/testdata/selection.py  src/gishant_scripts/sandbox/selection.py
```

Create `src/gishant_scripts/sandbox/__init__.py`:

```python
"""Sandbox tooling — generate and clean up test data across pipeline backends."""
```

`config.py` and `selection.py` have no `testdata` imports, so no edits are needed beyond the copy. Confirm with: `grep -rn "testdata" src/gishant_scripts/sandbox/` (expect no output).

- [ ] **Step 2: Write the ported tests**

Create `tests/unit/test_sandbox_selection.py`:

```python
"""Tests for sandbox sequence and shot selection."""

from __future__ import annotations

from gishant_scripts.sandbox.selection import SelectionScope


def test_episode_scope_when_no_patterns() -> None:
    scope = SelectionScope()
    assert scope.is_episode_scope
    assert scope.matches_sequence("ep_test_sq010")
    assert scope.matches_shot("ep_test_sq010", "ep_test_sq010_sh0010")


def test_sequence_glob_matches() -> None:
    scope = SelectionScope(sequence_patterns=["*sq020"])
    assert scope.is_sequence_scope
    assert scope.matches_sequence("ep_test_sq020")
    assert not scope.matches_sequence("ep_test_sq010")


def test_shot_scope_requires_sequence_and_shot_match() -> None:
    scope = SelectionScope(shot_patterns=["*_sh0030"])
    assert scope.is_shot_scope
    assert scope.matches_shot("ep_test_sq020", "ep_test_sq020_sh0030")
    assert not scope.matches_shot("ep_test_sq020", "ep_test_sq020_sh0010")


def test_patterns_normalized_and_deduped() -> None:
    scope = SelectionScope(sequence_patterns=[" a ", "a", "", "b"])
    assert tuple(scope.sequence_patterns) == ("a", "b")
```

Create `tests/unit/test_sandbox_config.py`:

```python
"""Tests for sandbox project-name configuration."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gishant_scripts.sandbox.config import (
    allowed_project_keys,
    load_projects,
    resolve_project,
)


@pytest.fixture
def projects_file(tmp_path: Path) -> Path:
    content = textwrap.dedent(
        """
        [projects.DEMO]
        shotgrid = "DEMO_SG"
        kitsu = "Demo Kitsu"
        ayon = "Demo_Ayon"
        storage = "Demo_Store"

        [projects.NOSTORE]
        shotgrid = "NoStore"
        kitsu = "NoStore"
        ayon = "NoStore"
        """
    )
    path = tmp_path / "projects.toml"
    path.write_text(content)
    return path


def test_load_and_resolve(projects_file: Path) -> None:
    cfg = resolve_project("DEMO", projects_file)
    assert cfg.kitsu == "Demo Kitsu"
    assert cfg.shotgrid == "DEMO_SG"
    assert cfg.ayon == "Demo_Ayon"
    assert cfg.storage == "Demo_Store"


def test_storage_defaults_to_shotgrid(projects_file: Path) -> None:
    cfg = resolve_project("NOSTORE", projects_file)
    assert cfg.storage == "NoStore"


def test_unknown_key_raises(projects_file: Path) -> None:
    with pytest.raises(KeyError):
        resolve_project("MISSING", projects_file)


def test_allowed_keys(projects_file: Path) -> None:
    assert allowed_project_keys(projects_file) == frozenset({"DEMO", "NOSTORE"})
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_sandbox_config.py tests/unit/test_sandbox_selection.py -v`
Expected: PASS (all)

- [ ] **Step 4: Commit**

```bash
git add src/gishant_scripts/sandbox/ tests/unit/test_sandbox_config.py tests/unit/test_sandbox_selection.py
git commit -m "feat(sandbox): scaffold package with config and selection modules"
```

---

### Task 2: Backend base layer

**Files:**
- Create: `src/gishant_scripts/sandbox/backends/__init__.py`
- Create: `src/gishant_scripts/sandbox/backends/base.py`
- Test: `tests/unit/test_sandbox_backends_base.py`

**Interfaces:**
- Produces: `Environment(str, Enum)` with `TEST = "test"`, `PRODUCTION = "production"`, and property `is_test -> bool`.
- Produces: `BackendUnavailable(Exception)`.
- Produces: `load_rdo_env() -> None`.
- Produces: `Backend(ABC)` — `__init__(self, raw_project_name: str, environment: Environment = Environment.TEST, project_config: ProjectConfig | None = None)`; abstract property `project_name -> str`. Subclasses add their own connection method.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sandbox_backends_base.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_backends_base.py -v`
Expected: FAIL with `ModuleNotFoundError: gishant_scripts.sandbox.backends`

- [ ] **Step 3: Write the implementation**

Create `src/gishant_scripts/sandbox/backends/base.py`:

```python
"""Backend connection layer for the sandbox tool.

Each backend owns its credentials, connection, and per-backend project-name
resolution. Orchestrators (generate / cleanup) call into these and keep the
operation logic (discovery, create, delete) to themselves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from gishant_scripts.sandbox.config import ProjectConfig

_RDO_ENV_PATH = Path.home() / ".rdo" / ".env"


class Environment(str, Enum):
    """Target server environment selected by the ``--server`` flag."""

    TEST = "test"
    PRODUCTION = "production"

    @property
    def is_test(self) -> bool:
        """Return True for the test environment."""
        return self is Environment.TEST


class BackendUnavailable(Exception):
    """Raised when a backend cannot be used (library missing or creds unset)."""


def load_rdo_env() -> None:
    """Load RDO credentials from ``~/.rdo/.env`` into the environment."""
    load_dotenv(_RDO_ENV_PATH)


class Backend(ABC):
    """Base for a single tracking backend: credentials, connection, name."""

    def __init__(
        self,
        raw_project_name: str,
        environment: Environment = Environment.TEST,
        project_config: ProjectConfig | None = None,
    ) -> None:
        self._raw_project_name = raw_project_name
        self._environment = environment
        self._project_config = project_config

    @property
    @abstractmethod
    def project_name(self) -> str:
        """Per-backend project name (from config, fallback to raw name)."""
```

Create `src/gishant_scripts/sandbox/backends/__init__.py`:

```python
"""Backend connection layer for the sandbox tool."""

from __future__ import annotations

from gishant_scripts.sandbox.backends.base import (
    Backend,
    BackendUnavailable,
    Environment,
    load_rdo_env,
)

__all__ = ["Backend", "BackendUnavailable", "Environment", "load_rdo_env"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_backends_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/backends/__init__.py src/gishant_scripts/sandbox/backends/base.py tests/unit/test_sandbox_backends_base.py
git commit -m "feat(sandbox): add backend base layer (Environment, Backend ABC)"
```

---

### Task 3: KitsuBackend

**Files:**
- Create: `src/gishant_scripts/sandbox/backends/kitsu.py`
- Test: `tests/unit/test_sandbox_backend_kitsu.py`
- Modify: `src/gishant_scripts/sandbox/backends/__init__.py` (export `KitsuBackend`)

**Interfaces:**
- Consumes: `Backend`, `BackendUnavailable`, `Environment`, `load_rdo_env`.
- Produces: `KitsuBackend(Backend)` with `project_name` (uses `config.kitsu`), `credentials() -> tuple[str | None, str | None]`, and `connect() -> object` (configured `gazu` module). `connect()` checks credentials first (raises `BackendUnavailable`), then imports `gazu` (raises `BackendUnavailable` if missing), then `set_host(host + "/api")` / `set_token(token)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sandbox_backend_kitsu.py`:

```python
"""Tests for KitsuBackend credential and name resolution."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.base import BackendUnavailable, Environment
from gishant_scripts.sandbox.backends.kitsu import KitsuBackend
from gishant_scripts.sandbox.config import ProjectConfig

_CFG = ProjectConfig(
    canonical_key="DEMO",
    shotgrid="DEMO_SG",
    kitsu="Demo Kitsu",
    ayon="Demo_Ayon",
    storage="Demo_Store",
)


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
    with pytest.raises(BackendUnavailable, match="RDO_KITSU_TEST_"):
        KitsuBackend("DEMO", environment=Environment.TEST).connect()
```

Note: tests set env vars explicitly; to keep them deterministic regardless of any real `~/.rdo/.env`, monkeypatch `load_rdo_env` to a no-op in a fixture if needed. Add at top of the test module:

```python
@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gishant_scripts.sandbox.backends.kitsu.load_rdo_env", lambda: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_backend_kitsu.py -v`
Expected: FAIL with `ModuleNotFoundError: ...backends.kitsu`

- [ ] **Step 3: Write the implementation**

Create `src/gishant_scripts/sandbox/backends/kitsu.py`:

```python
"""Kitsu/Zou backend connection."""

from __future__ import annotations

import os

from gishant_scripts.sandbox.backends.base import (
    Backend,
    BackendUnavailable,
    load_rdo_env,
)


class KitsuBackend(Backend):
    """Credentials, connection, and name for Kitsu (via gazu)."""

    @property
    def project_name(self) -> str:
        """Return the Kitsu-specific project name."""
        return self._project_config.kitsu if self._project_config else self._raw_project_name

    def credentials(self) -> tuple[str | None, str | None]:
        """Return ``(host, token)`` for the active environment."""
        load_rdo_env()
        if self._environment.is_test:
            return (
                os.environ.get("RDO_KITSU_TEST_HOST"),
                os.environ.get("RDO_KITSU_TEST_API_TOKEN"),
            )
        return os.environ.get("RDO_KITSU_HOST"), os.environ.get("RDO_KITSU_API_TOKEN")

    def connect(self) -> object:
        """Configure and return the ``gazu`` module. Raise BackendUnavailable on failure."""
        host, token = self.credentials()
        if not host or not token:
            prefix = "RDO_KITSU_TEST_" if self._environment.is_test else "RDO_KITSU_"
            msg = f"Kitsu: {prefix}HOST or {prefix}API_TOKEN not set"
            raise BackendUnavailable(msg)
        try:
            import gazu
        except ImportError as exc:
            msg = "Kitsu: gazu not installed"
            raise BackendUnavailable(msg) from exc
        gazu.set_host(host + "/api")
        gazu.set_token(token)
        return gazu
```

Add to `src/gishant_scripts/sandbox/backends/__init__.py`:

```python
from gishant_scripts.sandbox.backends.kitsu import KitsuBackend
```

and add `"KitsuBackend"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_backend_kitsu.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/backends/kitsu.py src/gishant_scripts/sandbox/backends/__init__.py tests/unit/test_sandbox_backend_kitsu.py
git commit -m "feat(sandbox): add KitsuBackend"
```

---

### Task 4: AyonBackend

**Files:**
- Create: `src/gishant_scripts/sandbox/backends/ayon.py`
- Test: `tests/unit/test_sandbox_backend_ayon.py`
- Modify: `src/gishant_scripts/sandbox/backends/__init__.py` (export `AyonBackend`)

**Interfaces:**
- Consumes: `Backend`, `BackendUnavailable`, `Environment`, `load_rdo_env`.
- Produces: `AyonBackend(Backend)` with `project_name` (uses `config.ayon`), `credentials() -> tuple[str | None, str | None]` returning `(server_url, api_key)`, and `connect() -> object` (configured `ayon_api` module). `connect()` checks creds first, imports `ayon_api`, sets `AYON_SERVER_URL`/`AYON_API_KEY` env, calls `create_connection()` if `not is_connection_created()`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sandbox_backend_ayon.py`:

```python
"""Tests for AyonBackend credential and name resolution."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.ayon import AyonBackend
from gishant_scripts.sandbox.backends.base import BackendUnavailable, Environment
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
    with pytest.raises(BackendUnavailable, match="AYON_TEST_"):
        AyonBackend("DEMO", environment=Environment.TEST).connect()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_backend_ayon.py -v`
Expected: FAIL with `ModuleNotFoundError: ...backends.ayon`

- [ ] **Step 3: Write the implementation**

Create `src/gishant_scripts/sandbox/backends/ayon.py`:

```python
"""AYON backend connection."""

from __future__ import annotations

import os

from gishant_scripts.sandbox.backends.base import (
    Backend,
    BackendUnavailable,
    load_rdo_env,
)


class AyonBackend(Backend):
    """Credentials, connection, and name for AYON (via ayon_api)."""

    @property
    def project_name(self) -> str:
        """Return the AYON-specific project name."""
        return self._project_config.ayon if self._project_config else self._raw_project_name

    def credentials(self) -> tuple[str | None, str | None]:
        """Return ``(server_url, api_key)`` for the active environment."""
        load_rdo_env()
        if self._environment.is_test:
            return (
                os.environ.get("AYON_TEST_SERVER_URL"),
                os.environ.get("AYON_TEST_API_KEY"),
            )
        return os.environ.get("AYON_SERVER_URL"), os.environ.get("AYON_API_KEY")

    def connect(self) -> object:
        """Configure and return the ``ayon_api`` module. Raise BackendUnavailable on failure."""
        server_url, api_key = self.credentials()
        if not server_url or not api_key:
            prefix = "AYON_TEST_" if self._environment.is_test else "AYON_"
            msg = f"AYON: {prefix}SERVER_URL or {prefix}API_KEY not set"
            raise BackendUnavailable(msg)
        try:
            import ayon_api
        except ImportError as exc:
            msg = "AYON: ayon_api not installed"
            raise BackendUnavailable(msg) from exc
        os.environ["AYON_SERVER_URL"] = server_url
        os.environ["AYON_API_KEY"] = api_key
        if not ayon_api.is_connection_created():
            ayon_api.create_connection()
        return ayon_api
```

Add to `backends/__init__.py`: `from gishant_scripts.sandbox.backends.ayon import AyonBackend` and add `"AyonBackend"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_backend_ayon.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/backends/ayon.py src/gishant_scripts/sandbox/backends/__init__.py tests/unit/test_sandbox_backend_ayon.py
git commit -m "feat(sandbox): add AyonBackend"
```

---

### Task 5: ShotGridBackend

**Files:**
- Create: `src/gishant_scripts/sandbox/backends/shotgrid.py`
- Test: `tests/unit/test_sandbox_backend_shotgrid.py`
- Modify: `src/gishant_scripts/sandbox/backends/__init__.py` (export `ShotGridBackend`)

**Interfaces:**
- Consumes: `Backend`, `BackendUnavailable`, `load_rdo_env`.
- Produces: `ShotGridBackend(Backend)` with `project_name` (uses `config.shotgrid`), `credentials() -> tuple[str | None, str | None, str | None]` returning `(url, script, api_key)` (no environment split), and `connect() -> object` returning a `shotgun_api3.Shotgun` instance. `connect()` checks creds first, then imports `shotgun_api3`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sandbox_backend_shotgrid.py`:

```python
"""Tests for ShotGridBackend credential and name resolution."""

from __future__ import annotations

import pytest

from gishant_scripts.sandbox.backends.base import BackendUnavailable, Environment
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
    with pytest.raises(BackendUnavailable, match="SHOTGRID_"):
        ShotGridBackend("DEMO").connect()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_backend_shotgrid.py -v`
Expected: FAIL with `ModuleNotFoundError: ...backends.shotgrid`

- [ ] **Step 3: Write the implementation**

Create `src/gishant_scripts/sandbox/backends/shotgrid.py`:

```python
"""ShotGrid backend connection."""

from __future__ import annotations

import os

from gishant_scripts.sandbox.backends.base import (
    Backend,
    BackendUnavailable,
    load_rdo_env,
)


class ShotGridBackend(Backend):
    """Credentials, connection, and name for ShotGrid (via shotgun_api3).

    ShotGrid credentials are environment-independent (one server for both
    test and production), unlike Kitsu and AYON.
    """

    @property
    def project_name(self) -> str:
        """Return the ShotGrid-specific project name."""
        return self._project_config.shotgrid if self._project_config else self._raw_project_name

    def credentials(self) -> tuple[str | None, str | None, str | None]:
        """Return ``(url, script_name, api_key)``."""
        load_rdo_env()
        return (
            os.environ.get("SHOTGRID_SERVER_URL"),
            os.environ.get("SHOTGRID_SCRIPT"),
            os.environ.get("SHOTGRID_API_KEY"),
        )

    def connect(self) -> object:
        """Return a ``shotgun_api3.Shotgun`` instance. Raise BackendUnavailable on failure."""
        url, script, key = self.credentials()
        if not url or not script or not key:
            msg = "ShotGrid: SHOTGRID_SERVER_URL, SHOTGRID_SCRIPT, or SHOTGRID_API_KEY not set"
            raise BackendUnavailable(msg)
        try:
            import shotgun_api3
        except ImportError as exc:
            msg = "ShotGrid: shotgun_api3 not installed"
            raise BackendUnavailable(msg) from exc
        return shotgun_api3.Shotgun(url, script_name=script, api_key=key)
```

Add to `backends/__init__.py`: `from gishant_scripts.sandbox.backends.shotgrid import ShotGridBackend` and add `"ShotGridBackend"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_backend_shotgrid.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/backends/shotgrid.py src/gishant_scripts/sandbox/backends/__init__.py tests/unit/test_sandbox_backend_shotgrid.py
git commit -m "feat(sandbox): add ShotGridBackend"
```

---

### Task 6: StorageBackend

**Files:**
- Create: `src/gishant_scripts/sandbox/backends/storage.py`
- Test: `tests/unit/test_sandbox_backend_storage.py`
- Modify: `src/gishant_scripts/sandbox/backends/__init__.py` (export `StorageBackend`)

**Interfaces:**
- Consumes: `Backend`.
- Produces: `StorageBackend(Backend)` with `project_name` (uses `config.storage`) and `resolve_root(ayon_project_name: str) -> Path`. `resolve_root` queries AYON anatomy `roots` (prefers a root named `work` with a `linux` path, else the first with `linux`), falling back to `Path("/projects")` on any error. No `connect()` (filesystem backend); name kept consistent via the abstract `project_name`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sandbox_backend_storage.py`:

```python
"""Tests for StorageBackend name resolution and NAS-root fallback."""

from __future__ import annotations

from pathlib import Path

from gishant_scripts.sandbox.backends.storage import StorageBackend
from gishant_scripts.sandbox.config import ProjectConfig

_CFG = ProjectConfig(
    canonical_key="DEMO",
    shotgrid="DEMO_SG",
    kitsu="Demo Kitsu",
    ayon="Demo_Ayon",
    storage="Demo_Store",
)


def test_project_name_uses_config() -> None:
    assert StorageBackend("DEMO", project_config=_CFG).project_name == "Demo_Store"


def test_project_name_falls_back_to_raw() -> None:
    assert StorageBackend("DEMO").project_name == "DEMO"


def test_resolve_root_falls_back_when_ayon_unavailable() -> None:
    # ayon_api is not connected / not configured in the test env, so resolve_root
    # must swallow the error and return the default root.
    root = StorageBackend("DEMO").resolve_root("Demo_Ayon")
    assert root == Path("/projects")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_backend_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: ...backends.storage`

- [ ] **Step 3: Write the implementation**

Create `src/gishant_scripts/sandbox/backends/storage.py`:

```python
"""NAS storage backend — path resolution for project folders on disk."""

from __future__ import annotations

import logging
from pathlib import Path

from gishant_scripts.sandbox.backends.base import Backend

_log = logging.getLogger(__name__)

_DEFAULT_ROOT = Path("/projects")


class StorageBackend(Backend):
    """Per-backend name plus NAS-root resolution for project folders."""

    @property
    def project_name(self) -> str:
        """Return the NAS folder name for this project."""
        return self._project_config.storage if self._project_config else self._raw_project_name

    def resolve_root(self, ayon_project_name: str) -> Path:
        """Resolve the NAS project root from AYON anatomy, fallback /projects.

        Requires an active AYON connection. Any failure (AYON unavailable,
        anatomy not configured) falls back to ``/projects``.
        """
        try:
            import ayon_api

            response = ayon_api.get(f"projects/{ayon_project_name}/anatomy")
            roots = response.data.get("roots", [])
            for root in roots:
                if root.get("name") == "work" and root.get("linux"):
                    return Path(root["linux"])
            for root in roots:
                if root.get("linux"):
                    return Path(root["linux"])
        except Exception:  # AYON unavailable or anatomy not configured
            _log.debug("Could not resolve storage root from AYON anatomy; using %s", _DEFAULT_ROOT)
        return _DEFAULT_ROOT
```

Add to `backends/__init__.py`: `from gishant_scripts.sandbox.backends.storage import StorageBackend` and add `"StorageBackend"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_backend_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/backends/storage.py src/gishant_scripts/sandbox/backends/__init__.py tests/unit/test_sandbox_backend_storage.py
git commit -m "feat(sandbox): add StorageBackend"
```

---

### Task 7: EpisodeGenerator — port to backend layer

**Files:**
- Create: `src/gishant_scripts/sandbox/generate.py` (ported from `testdata/generate.py`)
- Test: `tests/unit/test_sandbox_generate.py`

**Interfaces:**
- Consumes: `KitsuBackend`, `ShotGridBackend`, `AyonBackend`, `Environment`, `BackendUnavailable`, `SelectionScope`, `ProjectConfig`.
- Produces: `GenerationPlan` dataclass (`episode_name: str`, `sequences: list[str]`, `shots: dict[str, list[str]]`, property `total_shots: int`). Produces `EpisodeGenerator.__init__(self, project_name: str, episode_name: str, num_sequences: int, shots_per_sequence: int, *, console: Console, skip_kitsu=False, skip_shotgrid=False, skip_ayon=False, environment: Environment = Environment.TEST, selection_scope: SelectionScope | None = None, project_config: ProjectConfig | None = None)`, plus `plan() -> GenerationPlan`, `display_plan(plan)`, `execute(plan)`.

- [ ] **Step 1: Write the failing test (planning is pure — no backends touched)**

Create `tests/unit/test_sandbox_generate.py`:

```python
"""Tests for sandbox generation planning (pure, no backend calls)."""

from __future__ import annotations

from rich.console import Console

from gishant_scripts.sandbox.generate import EpisodeGenerator, GenerationPlan
from gishant_scripts.sandbox.selection import SelectionScope


def _gen(**kwargs) -> EpisodeGenerator:
    defaults = dict(
        project_name="DEMO",
        episode_name="ep_test",
        num_sequences=0,
        shots_per_sequence=0,
        console=Console(),
    )
    defaults.update(kwargs)
    return EpisodeGenerator(**defaults)


def test_count_based_plan() -> None:
    plan = _gen(num_sequences=2, shots_per_sequence=3).plan()
    assert plan.sequences == ["ep_test_sq010", "ep_test_sq020"]
    assert plan.total_shots == 6
    assert plan.shots["ep_test_sq010"] == [
        "ep_test_sq010_sh0010",
        "ep_test_sq010_sh0020",
        "ep_test_sq010_sh0030",
    ]


def test_sequence_glob_filters_generated() -> None:
    scope = SelectionScope(sequence_patterns=["*sq020"])
    plan = _gen(num_sequences=3, shots_per_sequence=0, selection_scope=scope).plan()
    assert plan.sequences == ["ep_test_sq020"]


def test_explicit_shot_infers_sequence() -> None:
    scope = SelectionScope(shot_patterns=["ep_test_sq050_sh0010"])
    plan = _gen(selection_scope=scope).plan()
    assert plan.sequences == ["ep_test_sq050"]
    assert plan.shots["ep_test_sq050"] == ["ep_test_sq050_sh0010"]


def test_generation_plan_total_shots() -> None:
    plan = GenerationPlan(episode_name="e", shots={"a": ["x", "y"], "b": ["z"]})
    assert plan.total_shots == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_generate.py -v`
Expected: FAIL with `ModuleNotFoundError: ...sandbox.generate`

- [ ] **Step 3: Port `generate.py`**

Start from a copy of the existing file, then apply the changes below:

```bash
cp src/gishant_scripts/testdata/generate.py src/gishant_scripts/sandbox/generate.py
```

Apply these edits to `src/gishant_scripts/sandbox/generate.py`:

1. **Imports:** change `from gishant_scripts.testdata.selection import SelectionScope` → `from gishant_scripts.sandbox.selection import SelectionScope`. Update the `TYPE_CHECKING` block to also import the backends and Environment:

```python
from gishant_scripts.sandbox.backends import (
    AyonBackend,
    BackendUnavailable,
    Environment,
    KitsuBackend,
    ShotGridBackend,
)
from gishant_scripts.sandbox.selection import SelectionScope

if TYPE_CHECKING:
    from rich.console import Console

    from gishant_scripts.sandbox.config import ProjectConfig
```

Remove the now-unused `import os`, `from pathlib import Path`, `from dotenv import load_dotenv`, and the module-level `_RDO_ENV_PATH` (the backends own all of that).

2. **`__init__`:** replace the `use_test_server: bool = False` parameter with `environment: Environment = Environment.TEST`. Store `self._environment = environment`. Keep all other params. Construct the three backends once:

```python
        self._kitsu = KitsuBackend(project_name, environment, project_config)
        self._shotgrid = ShotGridBackend(project_name, environment, project_config)
        self._ayon = AyonBackend(project_name, environment, project_config)
```

3. **Delete** the per-backend name properties (`_kitsu_name`, `_sg_name`, `_ayon_name`) and the credential/connection helpers (`_get_kitsu_creds`, `_get_shotgrid_creds`, `_get_ayon_creds`, `_setup_ayon_connection`). They are replaced by the backend objects.

4. **`plan()`, `_explicit_sequence_names()`, `_explicit_shot_names_for_sequence()`, `display_plan()`, `total_shots`, the `_is_glob_pattern`/`_sequence_from_shot_name` helpers, and the `GenerationPlan` dataclass:** keep verbatim. (`display_plan` already uses `self._skip_*`, no change.)

5. **`_create_kitsu(self, plan)`:** replace the import + creds + `gazu.set_host/set_token` preamble with:

```python
    def _create_kitsu(self, plan: GenerationPlan) -> None:
        """Create episode, sequences, and shots in Kitsu."""
        try:
            gazu = self._kitsu.connect()
        except BackendUnavailable as exc:
            self._console.print(f"[yellow]{exc} -- skipping[/]")
            return

        self._console.print("[bold cyan]Creating in Kitsu...[/]")
        project = gazu.project.get_project_by_name(self._kitsu.project_name)
        if not project:
            self._console.print(f"[red]Kitsu: project '{self._kitsu.project_name}' not found[/]")
            return
```

Keep the rest of the method body (episode/sequence/shot creation loop and summary print) unchanged.

6. **`_create_shotgrid(self, plan)`:** replace the import + creds + `Shotgun(...)` preamble with:

```python
    def _create_shotgrid(self, plan: GenerationPlan) -> None:
        """Create scene, sequences, and shots in ShotGrid using batch API."""
        try:
            sg = self._shotgrid.connect()
        except BackendUnavailable as exc:
            self._console.print(f"[yellow]{exc} -- skipping[/]")
            return

        self._console.print("[bold magenta]Creating in ShotGrid...[/]")
        project = sg.find_one("Project", [["name", "is", self._shotgrid.project_name]])
        if not project:
            self._console.print(f"[red]ShotGrid: project '{self._shotgrid.project_name}' not found[/]")
            return
```

Keep the rest (scene create, batch sequences, batch shots, summary) unchanged.

7. **`_create_ayon(self, plan)`:** replace the import + creds + `_setup_ayon_connection` preamble with:

```python
    def _create_ayon(self, plan: GenerationPlan) -> None:
        """Create episode, sequence, and shot folders in AYON."""
        try:
            ayon_api = self._ayon.connect()
        except BackendUnavailable as exc:
            self._console.print(f"[yellow]{exc} -- skipping[/]")
            return

        self._console.print("[bold green]Creating in AYON...[/]")
        proj = self._ayon.project_name
```

Then in the remaining body replace each `self._ayon_name` with `proj`. Keep the episodes-root lookup, folder creation loops, and summary unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_generate.py -v`
Expected: PASS

Also confirm no stale imports remain: `grep -n "testdata\|use_test_server\|_get_.*_creds\|_setup_ayon" src/gishant_scripts/sandbox/generate.py` (expect no output).

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/generate.py tests/unit/test_sandbox_generate.py
git commit -m "feat(sandbox): port EpisodeGenerator onto backend layer"
```

---

### Task 8: FolderCleanup (path mode) — port to backend layer

**Files:**
- Create: `src/gishant_scripts/sandbox/cleanup.py` (ported from `testdata/cleanup.py`)
- Test: `tests/unit/test_sandbox_cleanup.py`

**Interfaces:**
- Consumes: `KitsuBackend`, `ShotGridBackend`, `AyonBackend`, `StorageBackend`, `Environment`, `BackendUnavailable`, `ProjectConfig`.
- Produces: `FolderDeletionPlan` dataclass (unchanged fields, including `is_empty` property). Produces `FolderCleanup.__init__(self, project_name: str, path: str, console: Console, *, skip_kitsu=False, skip_shotgrid=False, skip_ayon=False, skip_storage=False, environment: Environment = Environment.TEST, project_config: ProjectConfig | None = None)`, plus `plan() -> FolderDeletionPlan`, `display_plan(plan)`, `execute(plan)`. Also produces module helpers `_is_glob(pattern) -> bool`, `_human_size(n) -> str` (reused by Task 9).

- [ ] **Step 1: Write the failing test (path resolution against a fake ayon_api)**

Create `tests/unit/test_sandbox_cleanup.py`:

```python
"""Tests for sandbox path-cleanup planning (fake AYON, no live calls)."""

from __future__ import annotations

import pytest
from rich.console import Console

from gishant_scripts.sandbox.cleanup import FolderCleanup, FolderDeletionPlan


def test_deletion_plan_is_empty_by_default() -> None:
    assert FolderDeletionPlan().is_empty


def test_deletion_plan_not_empty_with_folders() -> None:
    plan = FolderDeletionPlan(ayon_folders=[{"id": "1"}])
    assert not plan.is_empty


def test_empty_path_rejected() -> None:
    with pytest.raises(ValueError, match="path must not be empty"):
        FolderCleanup("DEMO", "/", Console())


class _FakeAyon:
    """Minimal stand-in for the ayon_api module used by _walk_ayon_path."""

    def __init__(self, folders: dict[str, dict]) -> None:
        self._by_path = folders

    def get_folder_by_path(self, _project: str, path: str) -> dict | None:
        return self._by_path.get(path)

    def get_folders(self, _project: str, parent_ids=None):  # noqa: ANN001
        if parent_ids is None:
            return list(self._by_path.values())
        parent = set(parent_ids)
        return [f for f in self._by_path.values() if f.get("parentId") in parent]


def test_walk_exact_path_returns_single_folder() -> None:
    fake = _FakeAyon({"assets/vehicles": {"id": "v1", "name": "vehicles", "parentId": None}})
    cleaner = FolderCleanup("DEMO", "/assets/vehicles", Console())
    matched = cleaner._walk_ayon_path(fake)
    assert [f["id"] for f in matched] == ["v1"]


def test_walk_glob_segment_matches_children() -> None:
    fake = _FakeAyon(
        {
            "assets": {"id": "a", "name": "assets", "parentId": None},
            "_child_car": {"id": "c1", "name": "car_suv", "parentId": "a"},
            "_child_van": {"id": "c2", "name": "van", "parentId": "a"},
        }
    )
    cleaner = FolderCleanup("DEMO", "/assets/car*", Console())
    matched = cleaner._walk_ayon_path(fake)
    assert [f["id"] for f in matched] == ["c1"]
```

Note: `_walk_ayon_path` calls `ayon_api_mod.get_folder_by_path(self._ayon.project_name, ...)`; with no `project_config`, `project_name` is `"DEMO"`. The fake ignores the project arg.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_cleanup.py -v`
Expected: FAIL with `ModuleNotFoundError: ...sandbox.cleanup`

- [ ] **Step 3: Port `cleanup.py`**

```bash
cp src/gishant_scripts/testdata/cleanup.py src/gishant_scripts/sandbox/cleanup.py
```

Apply these edits to `src/gishant_scripts/sandbox/cleanup.py`:

1. **Imports:** remove `import os`, `from dotenv import load_dotenv`, and the module-level `_RDO_ENV_PATH`. Add at top-level imports:

```python
from gishant_scripts.sandbox.backends import (
    AyonBackend,
    BackendUnavailable,
    Environment,
    KitsuBackend,
    ShotGridBackend,
    StorageBackend,
)
```

Change the `TYPE_CHECKING` import `from gishant_scripts.testdata.config import ProjectConfig` → `from gishant_scripts.sandbox.config import ProjectConfig`. Keep `import fnmatch`, `import logging`, `import shutil`, `from pathlib import Path`.

2. **`__init__`:** replace `use_test_server: bool = False` with `environment: Environment = Environment.TEST`; store `self._environment = environment`. Keep the path-normalization and `self._path`. Construct backends:

```python
        self._kitsu = KitsuBackend(project_name, environment, project_config)
        self._shotgrid = ShotGridBackend(project_name, environment, project_config)
        self._ayon = AyonBackend(project_name, environment, project_config)
        self._storage = StorageBackend(project_name, environment, project_config)
```

3. **Delete** the name properties (`_kitsu_name`, `_sg_name`, `_ayon_name`, `_storage_name`) and the cred/connection helpers (`_get_kitsu_creds`, `_get_shotgrid_creds`, `_get_ayon_creds`, `_setup_ayon_connection`).

4. **`_plan_ayon`:** replace its import/creds/connection preamble with:

```python
    def _plan_ayon(self, result: FolderDeletionPlan) -> None:
        """Resolve the AYON path and collect all descendant folders."""
        try:
            ayon_api = self._ayon.connect()
        except BackendUnavailable as exc:
            result.errors.append(str(exc))
            return

        try:
            self._console.print(f"[dim]AYON: resolving path {self._path}...[/]")
            matched = self._walk_ayon_path(ayon_api)
            if not matched:
                self._console.print(f"[yellow]AYON: no folders matched {self._path}[/]")
                return
            self._console.print(f"[dim]AYON: {len(matched)} match(es), collecting descendants...[/]")
            all_folders = self._collect_descendants(ayon_api, self._ayon.project_name, matched)
            result.ayon_folders.extend(all_folders)
            _log.info("AYON: %d folder(s) total (matched + descendants)", len(all_folders))
        except Exception as exc:  # ayon_api raises varied types
            msg = f"AYON: discovery failed -- {exc}"
            result.errors.append(msg)
            _log.warning(msg)
```

In `_walk_ayon_path`, replace the two `self._ayon_name` references with `self._ayon.project_name`.

5. **`_plan_kitsu`:** replace the import/creds/`set_host`/`set_token` preamble with:

```python
    def _plan_kitsu(self, result: FolderDeletionPlan) -> None:
        """Resolve Kitsu entities for each AYON folder via kitsuId or name fallback."""
        try:
            gazu = self._kitsu.connect()
        except BackendUnavailable as exc:
            result.errors.append(str(exc))
            return

        try:
            project = gazu.project.get_project_by_name(self._kitsu.project_name)
            if not project:
                _log.info("Kitsu: project %s not found", self._kitsu.project_name)
                return
```

Keep the rest of `_plan_kitsu` (the resolution loop and fallbacks) and `_add_kitsu_entity` unchanged.

6. **`_plan_shotgrid`:** replace the import/creds/`Shotgun(...)` preamble with:

```python
    def _plan_shotgrid(self, result: FolderDeletionPlan) -> None:
        """Discover ShotGrid entities by (entity_type, name) — one call per type."""
        try:
            sg = self._shotgrid.connect()
        except BackendUnavailable as exc:
            result.errors.append(str(exc))
            return

        try:
            project = sg.find_one("Project", [["name", "is", self._shotgrid.project_name]])
            if not project:
                _log.info("ShotGrid: project %s not found", self._shotgrid.project_name)
                return
```

Keep the rest of `_plan_shotgrid` unchanged.

7. **`_plan_storage`:** replace its `self._get_storage_root()` call and `self._storage_name` usage. The body becomes:

```python
    def _plan_storage(self, result: FolderDeletionPlan) -> None:
        """Discover NAS paths for plan roots whose AYON path is under /episodes/."""
        folder_ids = {f["id"] for f in result.ayon_folders}
        roots = [f for f in result.ayon_folders if f.get("parentId") not in folder_ids]
        episode_roots = [f for f in roots if f.get("path", "").startswith("/episodes/")]
        if not episode_roots:
            return

        storage_root = self._storage.resolve_root(self._ayon.project_name)

        for folder in episode_roots:
            ayon_rel = folder["path"].lstrip("/")
            nas_path = storage_root / self._storage.project_name / ayon_rel
            if not nas_path.exists():
                _log.info("Storage: path not found -- %s", nas_path)
                continue
            result.storage_paths.append(nas_path)
            total = sum(f.stat().st_size for f in nas_path.rglob("*") if f.is_file())
            result.storage_total_bytes += total
            _log.info("Storage: found %s (%s)", nas_path, _human_size(total))
```

**Delete** the `_get_storage_root` method (moved into `StorageBackend.resolve_root`).

8. **`execute` / `_execute_kitsu` / `_execute_shotgrid` / `_execute_ayon` / `_execute_storage`:** keep `execute`, `_execute_kitsu`, `_execute_storage` unchanged. In `_execute_shotgrid`, replace the import/creds/`Shotgun(...)` preamble with `sg = self._shotgrid.connect()` (it is only called when there is something to delete, so a `BackendUnavailable` here is unexpected; let it propagate). In `_execute_ayon`, replace `import ayon_api` + `proj = self._ayon_name` with `ayon_api = self._ayon.connect()` and `proj = self._ayon.project_name`.

9. **Keep verbatim:** `_is_glob`, `_truncate_id`, `_human_size`, `_add_rows_with_truncation`, `_collect_descendants`, `FolderDeletionPlan`, `_SG_TYPE_MAP`, `display_plan`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_cleanup.py -v`
Expected: PASS

Confirm cleanup: `grep -n "testdata\|use_test_server\|_get_.*_creds\|_setup_ayon\|_get_storage_root\|self\._ayon_name\|self\._kitsu_name\|self\._sg_name\|self\._storage_name" src/gishant_scripts/sandbox/cleanup.py` (expect no output).

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/cleanup.py tests/unit/test_sandbox_cleanup.py
git commit -m "feat(sandbox): port FolderCleanup onto backend layer"
```

---

### Task 9: ProjectRemoval — whole-project removal across all backends

**Files:**
- Modify: `src/gishant_scripts/sandbox/cleanup.py` (add `ProjectRemovalPlan` + `ProjectRemoval`)
- Test: `tests/unit/test_sandbox_project_removal.py`

**Interfaces:**
- Consumes: `KitsuBackend`, `ShotGridBackend`, `AyonBackend`, `StorageBackend`, `Environment`, `BackendUnavailable`, the module helpers `_human_size`, and `fnmatch`.
- Produces: `ProjectRemovalPlan` dataclass (`kitsu_projects: list[dict]`, `ayon_projects: list[dict]`, `shotgrid_projects: list[dict]`, `storage_paths: list[Path]`, `storage_total_bytes: int = 0`, `errors: list[str]`, property `is_empty`). Produces `ProjectRemoval.__init__(self, pattern: str, console: Console, *, skip_kitsu=False, skip_shotgrid=False, skip_ayon=False, skip_storage=False, environment: Environment = Environment.TEST)` with `plan() -> ProjectRemovalPlan`, `display_plan(plan)`, `execute(plan)`, and a static helper `_match(names, pattern)`.

Note: project mode glob-matches each backend's own project names — there is no canonical key, so backends are constructed with an empty `project_config` (per-backend name resolution is irrelevant here).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sandbox_project_removal.py`:

```python
"""Tests for whole-project removal planning (mocked backends)."""

from __future__ import annotations

from rich.console import Console

from gishant_scripts.sandbox.cleanup import ProjectRemoval, ProjectRemovalPlan


def test_plan_empty_by_default() -> None:
    assert ProjectRemovalPlan().is_empty


def test_match_glob_filters_names() -> None:
    names = ["_test_a", "_test_b", "WEDRO", "prod"]
    matched = ProjectRemoval._match(names, "_test*")
    assert matched == ["_test_a", "_test_b"]


def test_match_exact_name() -> None:
    assert ProjectRemoval._match(["WEDRO", "WED"], "WEDRO") == ["WEDRO"]


def test_remover_constructs_without_project_config() -> None:
    remover = ProjectRemoval("_test*", Console())
    # No canonical project; backends carry empty config.
    assert remover._kitsu._project_config is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_project_removal.py -v`
Expected: FAIL with `ImportError: cannot import name 'ProjectRemoval'`

- [ ] **Step 3: Add `ProjectRemovalPlan` and `ProjectRemoval` to `cleanup.py`**

Append to `src/gishant_scripts/sandbox/cleanup.py`:

```python
@dataclass
class ProjectRemovalPlan:
    """Whole projects matched for removal, grouped by backend."""

    kitsu_projects: list[dict] = field(default_factory=list)
    ayon_projects: list[dict] = field(default_factory=list)
    shotgrid_projects: list[dict] = field(default_factory=list)
    storage_paths: list[Path] = field(default_factory=list)
    storage_total_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True when no projects matched on any backend."""
        return not any(
            (
                self.kitsu_projects,
                self.ayon_projects,
                self.shotgrid_projects,
                self.storage_paths,
            )
        )


class ProjectRemoval:
    """Glob-match and delete whole projects across all four backends.

    Project names are matched independently on each backend (there is no
    canonical-key mapping for arbitrary projects). NAS storage is resolved
    from each matched AYON project's anatomy; projects that exist only on
    Kitsu cannot have storage resolved and are skipped for storage with a
    warning.

    Safety is provided by dry-run-by-default plus an explicit confirmation
    in the CLI -- there is no prefix guard.
    """

    def __init__(
        self,
        pattern: str,
        console: Console,
        *,
        skip_kitsu: bool = False,
        skip_shotgrid: bool = False,
        skip_ayon: bool = False,
        skip_storage: bool = False,
        environment: Environment = Environment.TEST,
    ) -> None:
        if not pattern.strip():
            msg = "pattern must not be empty"
            raise ValueError(msg)
        self._pattern = pattern.strip()
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._skip_storage = skip_storage
        self._environment = environment
        # No canonical key for arbitrary projects -> empty config.
        self._kitsu = KitsuBackend("", environment, None)
        self._shotgrid = ShotGridBackend("", environment, None)
        self._ayon = AyonBackend("", environment, None)
        self._storage = StorageBackend("", environment, None)

    @staticmethod
    def _match(names: list[str], pattern: str) -> list[str]:
        """Return names equal to or fnmatch-matching the pattern, stable order."""
        return [n for n in names if n == pattern or fnmatch.fnmatch(n, pattern)]

    # -- Planning -------------------------------------------------------

    def plan(self) -> ProjectRemovalPlan:
        """Discover matching projects across backends (read-only)."""
        result = ProjectRemovalPlan()
        if not self._skip_kitsu:
            self._plan_kitsu(result)
        if not self._skip_ayon:
            self._plan_ayon(result)
        if not self._skip_shotgrid:
            self._plan_shotgrid(result)
        if not self._skip_storage:
            self._plan_storage(result)
        return result

    def _plan_kitsu(self, result: ProjectRemovalPlan) -> None:
        try:
            gazu = self._kitsu.connect()
        except BackendUnavailable as exc:
            result.errors.append(str(exc))
            return
        try:
            self._console.print("[dim]Kitsu: matching projects...[/]")
            all_projects = gazu.project.all_projects()
            matched = self._match([p.get("name", "") for p in all_projects], self._pattern)
            result.kitsu_projects.extend(p for p in all_projects if p.get("name", "") in set(matched))
        except Exception as exc:  # gazu raises varied types
            result.errors.append(f"Kitsu: matching failed -- {exc}")

    def _plan_ayon(self, result: ProjectRemovalPlan) -> None:
        try:
            ayon_api = self._ayon.connect()
        except BackendUnavailable as exc:
            result.errors.append(str(exc))
            return
        try:
            self._console.print("[dim]AYON: matching projects...[/]")
            all_projects = list(ayon_api.get_projects(fields=["name"]))
            matched = set(self._match([p.get("name", "") for p in all_projects], self._pattern))
            result.ayon_projects.extend(p for p in all_projects if p.get("name", "") in matched)
        except Exception as exc:  # ayon_api raises varied types
            result.errors.append(f"AYON: matching failed -- {exc}")

    def _plan_shotgrid(self, result: ProjectRemovalPlan) -> None:
        try:
            sg = self._shotgrid.connect()
        except BackendUnavailable as exc:
            result.errors.append(str(exc))
            return
        try:
            self._console.print("[dim]ShotGrid: matching projects...[/]")
            all_projects = sg.find("Project", [], ["id", "name"])
            matched = set(self._match([p.get("name", "") for p in all_projects], self._pattern))
            result.shotgrid_projects.extend(p for p in all_projects if p.get("name", "") in matched)
        except Exception as exc:  # shotgun_api3 raises varied types
            result.errors.append(f"ShotGrid: matching failed -- {exc}")

    def _plan_storage(self, result: ProjectRemovalPlan) -> None:
        """Resolve NAS folders for matched AYON projects only."""
        if not result.ayon_projects:
            if result.kitsu_projects:
                result.errors.append(
                    "Storage: skipped -- no matching AYON projects to resolve NAS roots from"
                )
            return
        for project in result.ayon_projects:
            name = project.get("name", "")
            try:
                storage_root = self._storage.resolve_root(name)
            except Exception as exc:  # anatomy/filesystem errors
                result.errors.append(f"Storage: could not resolve root for {name} -- {exc}")
                continue
            nas_path = storage_root / name
            if not nas_path.exists():
                _log.info("Storage: path not found -- %s", nas_path)
                continue
            result.storage_paths.append(nas_path)
            total = sum(f.stat().st_size for f in nas_path.rglob("*") if f.is_file())
            result.storage_total_bytes += total

    # -- Display --------------------------------------------------------

    def display_plan(self, plan: ProjectRemovalPlan) -> None:
        """Print a Rich summary of the projects to be removed."""
        for err in plan.errors:
            self._console.print(f"[yellow]WARNING: {err}[/]")
        if plan.errors:
            self._console.print()
        if plan.is_empty:
            self._console.print("[dim]No matching projects found.[/]")
            return

        table = Table(title=f"Projects matching '{self._pattern}'", show_header=True, header_style="bold red")
        table.add_column("Backend", style="red")
        table.add_column("Project")
        for p in plan.kitsu_projects:
            table.add_row("Kitsu", p.get("name", ""))
        for p in plan.ayon_projects:
            table.add_row("AYON", p.get("name", ""))
        for p in plan.shotgrid_projects:
            table.add_row("ShotGrid", p.get("name", ""))
        for path in plan.storage_paths:
            table.add_row("Storage", str(path))
        self._console.print(Panel(table, border_style="red"))
        if plan.storage_paths:
            self._console.print(f"Storage total: [bold]{_human_size(plan.storage_total_bytes)}[/]")

    # -- Execution ------------------------------------------------------

    def execute(self, plan: ProjectRemovalPlan) -> None:
        """Delete matched projects from each backend."""
        if not self._skip_kitsu and plan.kitsu_projects:
            self._execute_kitsu(plan)
        if not self._skip_ayon and plan.ayon_projects:
            self._execute_ayon(plan)
        if not self._skip_shotgrid and plan.shotgrid_projects:
            self._execute_shotgrid(plan)
        if not self._skip_storage and plan.storage_paths:
            self._execute_storage(plan)

    def _execute_kitsu(self, plan: ProjectRemovalPlan) -> None:
        gazu = self._kitsu.connect()
        self._console.print("[bold cyan]Removing Kitsu projects...[/]")
        closed_status = gazu.project.get_project_status_by_name("Closed")
        for project in plan.kitsu_projects:
            name = project.get("name", "")
            try:
                # remove_project(force=True) returns HTTP 400 unless status is Closed first.
                if closed_status:
                    project["project_status_id"] = closed_status["id"]
                    gazu.project.update_project(project)
                gazu.project.remove_project(project, force=True)
                self._console.print(f"[green]OK[/] Kitsu: removed {name}")
            except Exception as exc:  # gazu raises varied types
                _log.warning("Kitsu: failed to remove %s -- %s", name, exc)
                self._console.print(f"[red]FAIL[/] Kitsu: {name} -- {exc}")

    def _execute_ayon(self, plan: ProjectRemovalPlan) -> None:
        ayon_api = self._ayon.connect()
        self._console.print("[bold green]Removing AYON projects...[/]")
        for project in plan.ayon_projects:
            name = project.get("name", "")
            try:
                ayon_api.delete_project(name)
                self._console.print(f"[green]OK[/] AYON: removed {name}")
            except Exception as exc:  # ayon_api raises varied types
                _log.warning("AYON: failed to remove %s -- %s", name, exc)
                self._console.print(f"[red]FAIL[/] AYON: {name} -- {exc}")

    def _execute_shotgrid(self, plan: ProjectRemovalPlan) -> None:
        sg = self._shotgrid.connect()
        self._console.print("[bold magenta]Removing ShotGrid projects...[/]")
        for project in plan.shotgrid_projects:
            name = project.get("name", "")
            try:
                sg.delete("Project", project["id"])
                self._console.print(f"[green]OK[/] ShotGrid: removed {name}")
            except Exception as exc:  # shotgun_api3 raises varied types
                _log.warning("ShotGrid: failed to remove %s -- %s", name, exc)
                self._console.print(f"[red]FAIL[/] ShotGrid: {name} -- {exc}")

    def _execute_storage(self, plan: ProjectRemovalPlan) -> None:
        self._console.print("[bold red]Removing NAS storage...[/]")
        for path in plan.storage_paths:
            try:
                shutil.rmtree(path)
                self._console.print(f"[green]OK[/] Storage: removed {path}")
            except Exception as exc:  # filesystem errors
                _log.warning("Storage: failed to remove %s -- %s", path, exc)
                self._console.print(f"[red]FAIL[/] Storage: {path} -- {exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_project_removal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/cleanup.py tests/unit/test_sandbox_project_removal.py
git commit -m "feat(sandbox): add ProjectRemoval for whole-project teardown"
```

---

### Task 10: CLI — `generate` and two-mode `cleanup`

**Files:**
- Create: `src/gishant_scripts/sandbox/cli.py` (ported from `testdata/cli.py`)
- Test: `tests/unit/test_sandbox_cli.py`

**Interfaces:**
- Consumes: `EpisodeGenerator`, `SelectionScope`, `FolderCleanup`, `ProjectRemoval`, `Environment`, `resolve_project`, `allowed_project_keys`.
- Produces: a Typer `app` (name `"sandbox"`) with exactly two commands: `generate` and `cleanup`. `cleanup` takes an optional positional `path` and an optional `--projects` option, mutually exclusive; both take `--server [test|production]` (default `test`).

- [ ] **Step 1: Write the failing test (CLI surface, all backends mocked away)**

Create `tests/unit/test_sandbox_cli.py`:

```python
"""Tests for the sandbox CLI surface (no live backend calls)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from gishant_scripts.sandbox.cleanup import FolderDeletionPlan, ProjectRemovalPlan
from gishant_scripts.sandbox.cli import app
from gishant_scripts.sandbox.generate import GenerationPlan

runner = CliRunner()


def test_cleanup_requires_path_or_projects() -> None:
    result = runner.invoke(app, ["cleanup"])
    assert result.exit_code != 0
    assert "path" in result.output.lower() or "projects" in result.output.lower()


def test_cleanup_rejects_both_path_and_projects() -> None:
    result = runner.invoke(app, ["cleanup", "/assets/x", "--projects", "_test*"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_cleanup_path_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCleanup:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> FolderDeletionPlan:
            return FolderDeletionPlan(ayon_folders=[{"id": "1", "name": "x", "path": "/assets/x"}])
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None:
            raise AssertionError("execute must not run in dry-run")

    monkeypatch.setattr("gishant_scripts.sandbox.cli.FolderCleanup", FakeCleanup)
    result = runner.invoke(app, ["cleanup", "/assets/x", "-p", "SGAYONTEST"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


def test_cleanup_projects_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRemoval:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> ProjectRemovalPlan:
            return ProjectRemovalPlan(kitsu_projects=[{"name": "_test_a"}])
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None:
            raise AssertionError("execute must not run in dry-run")

    monkeypatch.setattr("gishant_scripts.sandbox.cli.ProjectRemoval", FakeRemoval)
    result = runner.invoke(app, ["cleanup", "--projects", "_test*"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


def test_generate_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGenerator:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> GenerationPlan:
            return GenerationPlan(episode_name="ep_test", sequences=[], shots={})
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None:
            raise AssertionError("execute must not run in dry-run")

    class FakeCleanup:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> FolderDeletionPlan:
            return FolderDeletionPlan()
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None: ...

    monkeypatch.setattr("gishant_scripts.sandbox.cli.EpisodeGenerator", FakeGenerator)
    monkeypatch.setattr("gishant_scripts.sandbox.cli.FolderCleanup", FakeCleanup)
    result = runner.invoke(app, ["generate", "ep_test", "-p", "SGAYONTEST", "--sequences", "2"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sandbox_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: ...sandbox.cli`

- [ ] **Step 3: Write `cli.py`**

Create `src/gishant_scripts/sandbox/cli.py`. To keep imports patchable, import `FolderCleanup`, `ProjectRemoval`, `EpisodeGenerator` at module top (not lazily inside the command).

```python
"""CLI for the sandbox tool -- generate and cleanup test data."""

from __future__ import annotations

import typer
from rich.console import Console

from gishant_scripts.sandbox.backends import Environment
from gishant_scripts.sandbox.cleanup import FolderCleanup, ProjectRemoval
from gishant_scripts.sandbox.generate import EpisodeGenerator
from gishant_scripts.sandbox.selection import SelectionScope

app = typer.Typer(name="sandbox", help="Sandbox test data -- generate and cleanup.", no_args_is_help=True)
console = Console()


def _check_project(project_name: str) -> None:
    """Abort if project is not in the config allowlist."""
    from gishant_scripts.sandbox.config import allowed_project_keys

    allowed = allowed_project_keys()
    if project_name not in allowed:
        console.print(f"[bold red]REFUSED:[/] Project '{project_name}' is not in the config allowlist.")
        console.print(f"Allowed projects: {', '.join(sorted(allowed))}")
        raise typer.Exit(code=1)


def _print_server_mode(environment: Environment) -> None:
    """Display which server environment is active."""
    if environment.is_test:
        console.print("[bold yellow]Server: TEST[/]")
    else:
        console.print("[bold red]Server: PRODUCTION[/]")


@app.command("cleanup")
def cleanup_cmd(
    path: str | None = typer.Argument(
        None,
        help="AYON path to delete -- supports glob segments (e.g. /assets/vehicles, '/assets/*/car*')",
    ),
    projects: str | None = typer.Option(
        None,
        "--projects",
        help="Glob of whole project names to delete from ALL backends (e.g. '_test*'). Mutually exclusive with PATH.",
    ),
    project_name: str = typer.Option("SGAYONTEST", "--project", "-p", help="Project name for PATH mode (allowlist)"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview deletions (default) or execute them"),
    skip_kitsu: bool = typer.Option(False, help="Skip Kitsu"),
    skip_shotgrid: bool = typer.Option(False, help="Skip ShotGrid"),
    skip_ayon: bool = typer.Option(False, help="Skip AYON"),
    skip_storage: bool = typer.Option(False, help="Skip NAS storage"),
    server: Environment = typer.Option(Environment.TEST, "--server", help="Target environment: test or production"),
) -> None:
    """Delete an AYON path (PATH mode) or whole projects (--projects mode) across backends.

    Examples:
        gishant sandbox cleanup /assets/vehicles -p SGAYONTEST
        gishant sandbox cleanup '/assets/*/car*' --execute
        gishant sandbox cleanup --projects '_test*' --execute
        gishant sandbox cleanup --projects '_test*' --server production --execute

    Project mode (--projects) matches whole project names independently on each
    backend and deletes them from Kitsu, AYON, ShotGrid, and NAS storage. NAS
    storage is resolved only for matched AYON projects.
    """
    if path and projects:
        console.print("[bold red]ERROR:[/] PATH and --projects are mutually exclusive.")
        raise typer.Exit(code=1)
    if not path and not projects:
        console.print("[bold red]ERROR:[/] provide a PATH or --projects PATTERN.")
        raise typer.Exit(code=1)

    _print_server_mode(server)

    if projects:
        remover = ProjectRemoval(
            pattern=projects,
            console=console,
            skip_kitsu=skip_kitsu,
            skip_shotgrid=skip_shotgrid,
            skip_ayon=skip_ayon,
            skip_storage=skip_storage,
            environment=server,
        )
        plan = remover.plan()
        remover.display_plan(plan)
        if dry_run:
            console.print("\n[bold yellow]DRY RUN -- nothing was deleted. Pass --execute to delete.[/]")
            return
        if not typer.confirm(f"\nThis will PERMANENTLY delete all projects matching '{projects}'. Continue?"):
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(code=0)
        remover.execute(plan)
        console.print("\n[bold green]Project removal complete.[/]")
        return

    # PATH mode
    _check_project(project_name)
    from gishant_scripts.sandbox.config import resolve_project

    project_config = resolve_project(project_name)
    cleaner = FolderCleanup(
        project_name=project_name,
        path=path,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        skip_storage=skip_storage,
        environment=server,
        project_config=project_config,
    )
    plan = cleaner.plan()
    cleaner.display_plan(plan)
    if dry_run:
        console.print("\n[bold yellow]DRY RUN -- nothing was deleted. Pass --execute to delete.[/]")
        return
    if not typer.confirm(f"\nThis will PERMANENTLY delete all items above from '{project_name}'. Continue?"):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(code=0)
    cleaner.execute(plan)
    console.print("\n[bold green]Cleanup complete.[/]")


@app.command("generate")
def generate_cmd(
    episode_name: str = typer.Argument(..., help="Episode name in lowercase (e.g. ep_test)"),
    project_name: str = typer.Option("SGAYONTEST", "--project", "-p", help="Project name (must be in allowlist)"),
    sequences: int = typer.Option(0, "--sequences", "-s", help="Number of sequences to create"),
    shots_per_sequence: int = typer.Option(0, "--shots", help="Number of shots per sequence"),
    sequence_patterns: list[str] | None = typer.Option(None, "--sequence", help="Sequence name or glob to create"),
    shot_patterns: list[str] | None = typer.Option(None, "--shot", help="Shot name or glob to create"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Delete matching existing items first"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview what would be created"),
    skip_kitsu: bool = typer.Option(False, help="Skip Kitsu creation"),
    skip_shotgrid: bool = typer.Option(False, help="Skip ShotGrid creation"),
    skip_ayon: bool = typer.Option(False, help="Skip AYON creation"),
    server: Environment = typer.Option(Environment.TEST, "--server", help="Target environment: test or production"),
) -> None:
    """Create selected testdata across Kitsu, ShotGrid, and AYON.

    Examples:
        gishant sandbox generate ep_test --sequences 3 --shots 5
        gishant sandbox generate ep_test --sequence '*sq020' --shot '*_sh0030'
    """
    _check_project(project_name)
    _print_server_mode(server)

    from gishant_scripts.sandbox.config import resolve_project

    project_config = resolve_project(project_name)
    selection_scope = SelectionScope(sequence_patterns=sequence_patterns, shot_patterns=shot_patterns)

    generator = EpisodeGenerator(
        project_name=project_name,
        episode_name=episode_name,
        num_sequences=sequences,
        shots_per_sequence=shots_per_sequence,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        environment=server,
        selection_scope=selection_scope,
        project_config=project_config,
    )
    conflict_cleaner = FolderCleanup(
        project_name=project_name,
        path=f"/episodes/{episode_name}",
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        skip_storage=False,
        environment=server,
        project_config=project_config,
    )

    conflict_plan = conflict_cleaner.plan()
    if not conflict_plan.is_empty:
        console.print("\n[bold yellow]Existing matching items found.[/]")
        conflict_cleaner.display_plan(conflict_plan)
        if not replace_existing:
            console.print(
                "\n[bold yellow]Generation stopped. Pass --replace-existing to delete these items first.[/]"
            )
            return

    plan = generator.plan()
    generator.display_plan(plan)
    if dry_run:
        console.print("\n[bold yellow]DRY RUN -- nothing was created. Pass --execute to create.[/]")
        return
    if not typer.confirm(f"\nThis will create all items above in '{project_name}'. Continue?"):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(code=0)
    if replace_existing and not conflict_plan.is_empty:
        conflict_cleaner.execute(conflict_plan)
    generator.execute(plan)
    console.print("\n[bold green]Generation complete.[/]")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sandbox_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gishant_scripts/sandbox/cli.py tests/unit/test_sandbox_cli.py
git commit -m "feat(sandbox): add CLI with generate and two-mode cleanup"
```

---

### Task 11: Register `sandbox` in the parent CLI; update smoke test

**Files:**
- Modify: `src/gishant_scripts/cli.py:141-148`
- Modify: `tests/unit/test_cli_smoke.py:20,31-33`

**Interfaces:**
- Consumes: `gishant_scripts.sandbox.cli.app`.
- Produces: top-level `gishant sandbox` command group.

- [ ] **Step 1: Update the smoke test (failing first)**

In `tests/unit/test_cli_smoke.py`, change the parametrize list at line 20 from `"testdata"` to `"sandbox"`:

```python
    ["youtrack", "github", "media", "bookstack", "task-workspace", "sandbox"],
```

And update the nested-help test (lines ~31-33) to use the new command names:

```python
@pytest.mark.parametrize("cmd", ["generate", "cleanup"])
def test_sandbox_nested_help(cmd: str) -> None:
    result = runner.invoke(app, ["sandbox", cmd, "--help"])
    assert result.exit_code == 0, f"sandbox {cmd} --help failed: {result.output}"
```

Run: `uv run pytest tests/unit/test_cli_smoke.py -v`
Expected: FAIL (sandbox not registered yet)

- [ ] **Step 2: Register the sandbox subapp**

In `src/gishant_scripts/cli.py`, replace the `_reg_testdata` function (lines ~141-144) and its registration (line ~148):

```python
def _reg_sandbox() -> None:
    from gishant_scripts.sandbox.cli import app as sandbox_app

    app.add_typer(sandbox_app, name="sandbox")
```

```python
_register_subapp("sandbox", _reg_sandbox)
```

- [ ] **Step 3: Run the smoke test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_smoke.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/gishant_scripts/cli.py tests/unit/test_cli_smoke.py
git commit -m "feat(sandbox): register sandbox command group, retire testdata registration"
```

---

### Task 12: Delete the old `testdata` package and its tests

**Files:**
- Delete: `src/gishant_scripts/testdata/` (entire directory)
- Delete: `tests/unit/test_testdata_generate.py`, `tests/unit/test_testdata_config.py`, `tests/unit/test_testdata_cli.py`, `tests/unit/test_testdata_cleanup.py`, `tests/unit/test_testdata_selection.py`, `tests/unit/test_remove_projects.py`

- [ ] **Step 1: Remove the old package and tests**

```bash
git rm -r src/gishant_scripts/testdata
git rm tests/unit/test_testdata_generate.py tests/unit/test_testdata_config.py \
       tests/unit/test_testdata_cli.py tests/unit/test_testdata_cleanup.py \
       tests/unit/test_testdata_selection.py tests/unit/test_remove_projects.py
```

- [ ] **Step 2: Confirm no remaining references**

Run: `grep -rn "testdata\|remove_projects" src/ tests/`
Expected: no output. (Historical git history and the spec/plan docs may still mention it — that is fine.)

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: PASS (all). No test connects to a real backend.

- [ ] **Step 4: Lint/typecheck if configured**

Run: `uv run ruff check src/gishant_scripts/sandbox tests/unit/test_sandbox_*.py`
Expected: clean (fix any reported issues).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(sandbox): remove legacy testdata package and tests"
```

---

## Self-Review notes

- **Spec coverage:** package rename (T1–T12), two-command surface (T10), fold project removal into cleanup (T9–T10), `--server test|production` default test (T2 enum, T10 wiring), per-backend layer Approach A (T2–T6), glob project removal no `_` guard (T9), all-four-backend removal (T9), storage caveat for Kitsu-only projects (T9 `_plan_storage`), mutual-exclusion validation (T10), tests rewritten + old deleted (T1, T7–T12), parent registration (T11). All spec sections map to tasks.
- **No live execution:** every test uses pure data, fakes, or mocked backend symbols; no task invokes a real connection.
- **Type consistency:** backend constructors are `(raw_project_name, environment, project_config)` everywhere; orchestrators expose `.project_name` / `.connect()` / `StorageBackend.resolve_root(ayon_project_name)` consistently across T7–T9.

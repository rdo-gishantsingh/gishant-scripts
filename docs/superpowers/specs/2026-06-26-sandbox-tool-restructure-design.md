# Sandbox tool restructure — design

**Date:** 2026-06-26
**Status:** Approved (pending spec review)

## Summary

Restructure the `testdata` multi-backend VFX data tool into a cleaner package
named `sandbox`. Reduce the command surface from four commands to **two**
(`generate`, `cleanup`), fold whole-project removal into `cleanup`, replace the
`--test-server` boolean with a `--server test|production` flag, and extract the
duplicated credential/connection/name-resolution code into a per-backend
backend layer (Approach A).

This is a refactor: `generate` and path-based `cleanup` keep their existing
behavior. The new work is the structural extraction, the renamed package, the
folded-in project removal, and the flag change.

## Background — current state

`src/gishant_scripts/testdata/` mirrors a production hierarchy (episode →
sequence → shot, plus assets) across four backends: Kitsu/Zou, ShotGrid, AYON,
and NAS storage.

| File | Role |
|---|---|
| `cli.py` | Typer app, 4 commands: `cleanup-path`, `generate`, `remove-projects` |
| `cleanup.py` | `FolderCleanup` — resolve AYON path (glob segments) → plan → delete from 4 backends |
| `generate.py` | `EpisodeGenerator` — create hierarchy across Kitsu/SG/AYON |
| `remove_projects.py` | bulk-delete whole projects by name prefix (Kitsu + AYON) |
| `config.py` + `projects.toml` | per-backend project-name mapping |
| `selection.py` | `SelectionScope` — glob/exact sequence + shot filtering |

**Problems being fixed:**

1. Four commands; the goal is two.
2. Credential helpers (`_get_kitsu_creds`, `_get_shotgrid_creds`,
   `_get_ayon_creds`, `_setup_ayon_connection`) and per-backend name properties
   (`_kitsu_name`, `_sg_name`, `_ayon_name`, `_storage_name`) are copy-pasted
   across `cleanup.py`, `generate.py`, and `remove_projects.py`.
3. The existing test suite (`tests/unit/test_testdata_*`,
   `test_remove_projects.py`) is partly stale — it references `EpisodeCleanup` /
   `DeletionPlan` symbols that no longer match the code (`FolderCleanup` /
   `FolderDeletionPlan`).

**What is kept (good as-is):**

- The path-glob cleanup (`_walk_ayon_path` + `_collect_descendants`), with AYON
  as source of truth and `kitsuId`/name matching for other backends.
- The `plan() → display_plan() → execute()` pattern: dry-run by default, Rich
  preview, explicit confirmation.
- The `projects.toml` per-backend name config.

## Decisions (locked)

- Rename package `testdata` → `sandbox`. Commands: `gishant sandbox generate`,
  `gishant sandbox cleanup`.
- Delete `remove_projects.py`; fold whole-project removal into `cleanup`.
- `cleanup` mode selection: **path positional (default)** vs **`--projects
  PREFIX_GLOB` flag**. Mutually exclusive.
- Project-removal mode uses a **glob** (no `_`-prefix guard). Safety is dry-run
  default + explicit `--execute` + confirmation prompt.
- Project-removal mode deletes from **all four backends**.
- Replace `--test-server` boolean with `--server [test|production]`, default
  `test`, on both commands.
- Structure: **Approach A** — a per-backend layer owning credentials,
  connection, and name resolution; orchestrators keep operation logic.

## Architecture

### Module layout

```
src/gishant_scripts/sandbox/
├── __init__.py
├── cli.py              # Typer app: generate, cleanup
├── config.py           # ProjectConfig, resolve_project, allowed_project_keys (unchanged)
├── projects.toml       # unchanged
├── selection.py        # SelectionScope (unchanged)
├── backends/
│   ├── __init__.py     # re-exports; Environment, BackendUnavailable
│   ├── base.py         # Backend ABC, Environment enum, .env loading
│   ├── kitsu.py        # KitsuBackend
│   ├── shotgrid.py     # ShotGridBackend
│   ├── ayon.py         # AyonBackend
│   └── storage.py      # StorageBackend
├── generate.py         # EpisodeGenerator (orchestrator)
└── cleanup.py          # FolderCleanup (path mode) + ProjectRemoval (projects mode)
```

`remove_projects.py` is deleted.

### Backend layer (`backends/`)

`base.py`:

- `class Environment(str, Enum)`: `TEST = "test"`, `PRODUCTION = "production"`.
- `class BackendUnavailable(Exception)`: raised when a backend's library is not
  importable or its credentials are not set. Orchestrators catch this uniformly
  and surface a warning (preserving today's "… not installed / not set —
  skipping" UX).
- `class Backend(ABC)`: holds `project_config: ProjectConfig | None`,
  `raw_project_name: str`, `environment: Environment`. Subclasses implement:
  - `project_name -> str` — the per-backend name from `project_config`, falling
    back to `raw_project_name` when no config.
  - `connect()` — set up and return the backend client; raise
    `BackendUnavailable` on missing lib or creds.
- Shared `.env` loading helper (`~/.rdo/.env` via `python-dotenv`).

Per backend (credentials, connection, name only — **no** discovery/create/delete
logic, which stays in orchestrators):

| Backend | Env vars (test → production) | `connect()` returns | `project_name` source |
|---|---|---|---|
| `KitsuBackend` | `RDO_KITSU_TEST_HOST/_API_TOKEN` → `RDO_KITSU_HOST/_API_TOKEN` | configured `gazu` module (`set_host(host+"/api")`, `set_token`) | `config.kitsu` |
| `AyonBackend` | `AYON_TEST_SERVER_URL/_API_KEY` → `AYON_SERVER_URL/_API_KEY` | configured `ayon_api` module (env set + `create_connection` if needed) | `config.ayon` |
| `ShotGridBackend` | `SHOTGRID_SERVER_URL/_SCRIPT/_API_KEY` (no test/prod split — same as today) | `shotgun_api3.Shotgun(...)` instance | `config.shotgrid` |
| `StorageBackend` | n/a (filesystem) | NAS root `Path`, resolved from AYON anatomy `roots` (prefer `work`/`linux`), fallback `/projects` | `config.storage` |

### Orchestrators

`generate.py` — `EpisodeGenerator`:

- Keeps `plan()` (pure computation), `display_plan()`, `execute()` and all
  current flags: `--sequences`, `--shots`, `--sequence`, `--shot`,
  `--replace-existing`.
- Internally constructs `KitsuBackend` / `ShotGridBackend` / `AyonBackend` from
  `project_config` + `environment` + skip flags; uses `backend.connect()` and
  `backend.project_name` instead of inline cred/name code.
- The pre-create conflict check that builds a `FolderCleanup` for
  `/episodes/{episode}` stays.

`cleanup.py` — two orchestrators:

- `FolderCleanup` (path mode): unchanged discovery/planning/execution behavior
  (the path-glob resolution, cross-backend matching, `force=True` cascade
  delete, NAS storage). Refactored to use the backend layer.
- `ProjectRemoval` (project mode, refactor of `remove_projects.py`):
  - Glob-matches project names **independently on each backend**
    (`fnmatch` against each server's project list).
  - `plan()` collects matched project names per backend; `display_plan()` shows
    them in a Rich table; `execute()` deletes whole projects:
    - Kitsu: set status to "Closed", then `remove_project(force=True)` (the
      existing HTTP-400 workaround).
    - AYON: `delete_project(name)`.
    - ShotGrid: delete the `Project` entity (`sg.delete("Project", id)`).
    - Storage: `shutil.rmtree` of the project folder under the NAS root.
  - Storage caveat: the NAS folder is resolved from each matched **AYON**
    project's anatomy (folder name = AYON project name). Projects that exist
    only in Kitsu (no AYON match) cannot have storage resolved → skipped with a
    warning shown in the plan. Documented in `--help`.
  - Respects `--skip-kitsu/--skip-shotgrid/--skip-ayon/--skip-storage`.

### CLI (`cli.py`)

`cleanup` command:

```
gishant sandbox cleanup /assets/vehicles -p SGAYONTEST        # path mode (default)
gishant sandbox cleanup '/assets/*/car*' --execute
gishant sandbox cleanup --projects '_test*' --execute         # project-removal mode
gishant sandbox cleanup --projects '_test*' --server production
```

- Positional `PATH` (optional) and `--projects PREFIX_GLOB` (optional) are
  mutually exclusive. Passing both, or neither, is a usage error.
- Path mode: `--project` is allowlist-checked (`_check_project`). Project mode:
  no allowlist, no `_` guard.
- Both modes: `--dry-run/--execute` (dry-run default), confirmation prompt
  before any deletion, `--skip-*` flags, `--server`.

`generate` command: unchanged flags, plus the `--server` change.

Flag change (both commands): remove `--test-server: bool`; add
`--server: Environment = Environment.TEST`. `_print_server_mode` updated to read
the enum. Env mapping: `production` → base env vars, `test` → `*_TEST_*` vars.

Registration in `src/gishant_scripts/cli.py`: rename `_reg_testdata` →
`_reg_sandbox`, import from `gishant_scripts.sandbox.cli`, register with
`name="sandbox"`, update `_register_subapp` call.

## Testing

Rewrite the suite as `tests/unit/test_sandbox_*` (delete the old
`test_testdata_*` and `test_remove_projects.py`):

- `SelectionScope` glob/exact matching (port existing).
- `config` load/resolve/allowlist (port existing).
- `EpisodeGenerator.plan()` — pure naming hierarchy, selection scoping.
- `FolderCleanup` planning — path-glob resolution against a fake AYON module.
- `ProjectRemoval` — glob-matching project names across mocked backends.
- Per-backend `project_name` resolution and env-var selection (test vs
  production) with mocked env and imported libs; `BackendUnavailable` on missing
  creds/lib.
- CLI smoke test: update `testdata` → `sandbox`, assert both subcommands'
  `--help` exit 0, and mutual-exclusion validation for `cleanup`.

## Migration / removal

After the `sandbox/` package and new tests are green:

- Delete `src/gishant_scripts/testdata/` entirely.
- Delete old tests: `test_testdata_generate.py`, `test_testdata_config.py`,
  `test_testdata_cli.py`, `test_testdata_cleanup.py`,
  `test_testdata_selection.py`, `test_remove_projects.py`.
- Confirm no remaining references to `testdata` outside historical git/specs.

## Out of scope

- Changing the cross-backend matching strategy (kitsuId/name/code lookups).
- Changing `projects.toml` schema or `SelectionScope` semantics.
- Per-environment ShotGrid credentials (SG remains environment-independent, as
  today).

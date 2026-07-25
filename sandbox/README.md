# sandbox — test-data generator and cleaner

Creates and deletes sandbox episodes/sequences/shots across four backends at
once — Kitsu, ShotGrid, AYON and NAS storage — keeping the per-backend project
names in sync. **The cleanup side is destructive**; it defaults to a dry run and
to the test servers.

## Setup

```bash
cd sandbox && uv sync
```

Credentials are read from `~/.rdo/.env` (never from this repo):

| Backend  | Test (`--server test`, default)                                                   | Production (`--server production`)      |
| -------- | --------------------------------------------------------------------------------- | --------------------------------------- |
| AYON     | `AYON_TEST_SERVER_URL`, `AYON_TEST_API_KEY`                                       | `AYON_SERVER_URL`, `AYON_API_KEY`       |
| Kitsu    | `RDO_KITSU_TEST_HOST`, `RDO_KITSU_TEST_API_TOKEN`                                 | `RDO_KITSU_HOST`, `RDO_KITSU_API_TOKEN` |
| ShotGrid | `SHOTGRID_SERVER_URL`, `SHOTGRID_SCRIPT`, `SHOTGRID_API_KEY` (no test/prod split) | same                                    |

`projects.toml` is the allowlist: a `--project` key must have a block there, and
that block maps the canonical key to the per-backend project name. Add a
`[projects.KEY]` block for any new project.

## Run

From the **repo root** — `sandbox` only imports when the repo root is the
working directory.

```bash
uv run --project sandbox python -m sandbox.cli --help

# create: 3 sequences x 5 shots, preview then execute
uv run --project sandbox python -m sandbox.cli generate ep_test -p SGAYONTEST --sequences 3 --shots 5
uv run --project sandbox python -m sandbox.cli generate ep_test -p SGAYONTEST --sequences 3 --shots 5 --execute

# create only what matches a glob
uv run --project sandbox python -m sandbox.cli generate ep_test --sequence '*sq020' --shot '*_sh0030'

# delete one AYON path across all backends
uv run --project sandbox python -m sandbox.cli cleanup /assets/vehicles -p SGAYONTEST
uv run --project sandbox python -m sandbox.cli cleanup '/assets/*/car*' -p SGAYONTEST --execute

# delete whole projects by name glob, narrowed to a creation window
uv run --project sandbox python -m sandbox.cli cleanup --projects '_test*' --execute
uv run --project sandbox python -m sandbox.cli cleanup '/episodes/hitro104/*' --created-after 2026-07-09
```

Both commands print the plan and stop; `--execute` runs it and still asks for
confirmation. `--skip-kitsu` / `--skip-shotgrid` / `--skip-ayon` /
`--skip-storage` narrow the blast radius.

## Gotchas

- **The backend client libraries are not declared as dependencies.**
  `pyproject.toml` lists only typer, rich and python-dotenv, while the backends
  import `ayon_api`, `gazu` and `shotgun_api3` lazily. After a plain `uv sync`
  every dry run works and every `--execute` dies with
  `BackendUnavailableError: ... not installed`. Install them into the venv
  before executing:

  ```bash
  uv pip install --python sandbox/.venv/bin/python ayon-python-api gazu shotgun-api3
  ```
- **The `sandbox` console script is not installed** — `pyproject.toml` declares
  it, but with no `[build-system]` `uv sync` installs dependencies only.
  `python -m sandbox.cli` is the entry point.
- **The docstring examples inside `cli.py` are stale.** They read
  `gishant sandbox cleanup ...`; that umbrella CLI no longer exists.
- `--server production` is a real option and it points at the live trackers.
  There is no allowlist check on `--projects` mode — a glob like `'*'` would
  match everything the credentials can see.
- NAS roots come from AYON project anatomy and silently fall back to
  `/projects` when AYON is unreachable, so `--skip-storage` is worth passing if
  AYON is down.

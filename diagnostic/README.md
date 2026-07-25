# diagnostic — DCC diagnostic runner

Runs a diagnostic Python script inside Maya (Linux host, over SSH) or Unreal
(Windows host, over SSH) with a fully resolved AYON context, then fetches back
the structured JSON result the script wrote. The `pipeline` subcommand runs both
DCCs in parallel and reports the worst status of the two.

## Setup

```bash
cd diagnostic && uv sync
```

Credentials do not come from this repo. The test-server guard reads
`~/.rdo/.env` **on the target box** over SSH and requires
`AYON_TEST_SERVER_URL` and `AYON_TEST_API_KEY` (`RDO_KITSU_TEST_HOST` /
`RDO_KITSU_TEST_API_TOKEN` optional).

Everything else is a default in `config.py`, each overridable by env var —
`MAYA_BIN`, `UNREAL_BIN`, `AYON_LAUNCHER_PATH`, `AYON_STORAGE_DIR`,
`DIAGNOSTIC_BASE_DIR`, `NAS_HOSTNAME`, and their `*_WIN` counterparts.

## Run

Always from the **repo root** — `diagnostic` is a plain package directory, so it
only imports when the repo root is the working directory.

```bash
uv run --project diagnostic python -m diagnostic --help

uv run --project diagnostic python -m diagnostic maya \
    --project SGAYONTEST \
    --folder /episodes/ep_test/sq010/sh0010 \
    --script /tech/users/gisi/dev/_diagnostic/issues/<issue>/check_fps.py

uv run --project diagnostic python -m diagnostic unreal \
    --project SGAYONTEST --folder /episodes/ep_test/sq010/sh0010 \
    --script /tech/users/gisi/dev/_diagnostic/issues/<issue>/check_fps.py \
    --uproject /projects/SGAYONTEST/unreal/SGAYONTEST.uproject

uv run --project diagnostic python -m diagnostic pipeline \
    --project SGAYONTEST --folder /episodes/ep_test/sq010/sh0010 \
    --maya-script <path> --unreal-script <path> --uproject <path>
```

Exit codes: `0` pass, `1` fail, `2` error, `3` test-server guard refused.

Results land under `DIAGNOSTIC_BASE_DIR` (default
`/tech/users/gisi/dev/_diagnostic`) in `issues/<issue>/results/`, where
`<issue>` is the parent directory name of the script you passed. A live log is
mirrored to `~/.cache/gishant-diagnostic/<issue>/`.

## Gotchas

- **The `dcc-run` console script is not installed.** `pyproject.toml` declares
  it, but there is no `[build-system]`, so `uv sync` installs dependencies only,
  never the package. `python -m diagnostic` is the entry point.
- **Runs must target a test server.** `test_server_guard` hard-fails on missing
  keys and rejects any AYON/Kitsu URL that is not `localhost`, `127.0.0.1` or
  `10.1.69.24` — exit 3, nothing is launched.
- **Two paths still point at the pre-restructure layout and no longer resolve:**
  - `bash_builder.py:14` — the run preamble is
    `set -e && ... && source <repo>/.venv/bin/activate`, and there is no
    repo-root venv any more (each
    tool has its own). `ssh_runner` feeds that preamble to `bash -s` in **both**
    local and SSH modes, so every Maya run now aborts before Maya launches.
  - `ayon_env.py:34` — `_PROJECT_ROOT = parents[3]` resolves to `~/dev`, not the
    repo root, so the `_SRC` and `_SITE_PKGS` entries it appends to `PYTHONPATH`
    point at directories that do not exist.
- `test_server_guard.py` lives in the package, not in a test directory — it is
  production code despite the name (`__test__ = False` keeps pytest off it).

# Local pipeline — AYON + Kitsu + rdo_kitsu processor

A self-contained local mirror of the production pipeline for testing the `rdo_kitsu`
add-on: the AYON server, the Kitsu (zou) server, and the sync processor, all restored
from the latest production database backups and pointed **only** at this machine
(`10.1.69.24`).

## Setup

This directory owns its venv — `ayon_api`, `requests` and `rich` for the scripts
the orchestrator shells out to. Create it once:

```bash
cd local_pipeline && uv sync
```

## One command (hands-off)

```bash
sudo scripts/restore-local-stack.sh          # full run
sudo scripts/restore-local-stack.sh --dry-run   # preview, touches nothing
```

It runs, in order:

1. **Restore** both databases from the latest hourly backups (`sync-and-restore-databases.sh`).
2. **Migrate** Kitsu 0.20.51 → 1.0.57 (`zou-upgrade-1057.sh`, two-phase, snapshot-first).
3. **Add-on + dev bundle**: log in as the `~/.rdo/.env` user (`gisi`), install `rdo_kitsu`
   0.3.3 if missing, and clone the current staging bundle into a dev bundle owned by that
   user (`install_rdo_kitsu.py`).
4. **Localize** (`localize_kitsu_addon.py`): mint a local Kitsu bot token and point the
   `rdo_kitsu` settings at the local Kitsu (`10.1.69.24:8090`) — written to both the
   `production` variant (the add-on's server-side endpoints and the processor read it) and
   the dev bundle's own variant (for the launcher). Never prod URLs/keys.
5. **Processor up** (`processor/up-local-stack.sh`): start kafka + listener + consumer.
6. **Full sync** + **verify**: request a sync for every paired project, then confirm AYON,
   both Kitsu ports, the processor, and local-only settings.

## Layout

| Path            | What                                                        |
| --------------- | ----------------------------------------------------------- |
| `ayon-server/`  | AYON server docker stack (`:5000`) + `.env`                 |
| `kitsu-server/` | Kitsu/zou docker stack — zou `:5005`, nginx gateway `:8090` |
| `processor/`    | `rdo_kitsu` processor override + `up-local-stack.sh`        |
| `scripts/`      | the orchestrator + restore/migrate/install/localize scripts |

## Notes

- **Kitsu URL is `:8090`** (the nginx gateway), not `:5005` (zou-direct). zou 1.0.57 serves
  root-only; the add-on and gazu need the `/api` + `/socket.io` gateway.
- The migration (`zou upgrade-db` is broken for a pre-1.0.0 dump) is done directly in two
  phases; see `scripts/zou_upgrade_1057.py`.
- The processor's base compose lives in the external `rdo-ayon-kitsu` repo
  (overridable via `PROCESSOR_COMPOSE`).
- Requires: root (for the backup mount), the `gisi` credentials in `~/.rdo/.env`, this
  directory's own venv, and the external `rdo-ayon-kitsu` checkout.

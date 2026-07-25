# ayon-server — local AYON docker stack

The local AYON server (`:5000`) plus its Postgres, Redis, ASH worker, pgAdmin
(`:9080`) and Dozzle log viewer (`:9999`). This is the AYON half of the
`local_pipeline` stack; see `../README.md` for the full restore orchestration.

## Setup

```bash
cp .env.example .env      # then fill in AYON_API_KEY
docker compose config     # sanity-check the merged config
```

Requires, all outside this repo:

- the `ayon-docker` checkout at `/home/gisi/dev/repos/ayon-docker` — it is the
  build context for the `server` image and supplies the `addons/`, `storage/`
  and `backend/` bind mounts
- the external docker network `pipeline_network`
  (`docker network create pipeline_network` if missing)

## Run

```bash
docker compose up -d
docker compose ps
docker compose logs -f server
docker compose down
```

Restore a production dump into the local DB (5 stages: stage, extract, strip
thumbnails, restore, cleanup):

```bash
./restore-db.sh /path/to/backup.sql.gz
./restore-db.sh /path/to/backup.sql.gz --keep-staging --skip-thumbnail-removal
./restore-db.sh /path/to/backup.sql.gz --filter     # needs FILTER_PATTERNS set in the script
```

It stages through `/home/gisi/dev/backups/ayon`, uses `pigz`/`pv` when present,
and stops the `server`/`worker` services while the restore runs.

## Gotchas

- **`.env` is gitignored and its history was purged.** `.env.example` is the
  committed reference; the real key lives only on this box.
- **The pgAdmin `servers.json` bind mount is stale.** `docker-compose.yml` still
  mounts `src/gishant_scripts/local_pipeline/ayon-server/pgadmin/servers.json`,
  a path that no longer exists after the repo restructure — docker will create
  an empty directory there and pgAdmin starts with no pre-registered server.
  The file itself is here at `pgadmin/servers.json`.
- **`AYON_POSTGRES_URL` must point straight at Postgres, not PgBouncer** —
  asyncpg does not work through it.
- Most compose variables have inline defaults (`${VAR:-default}`), so a missing
  `.env` starts a working-but-default stack rather than failing loudly. The
  `worker` service in particular falls back to a hardcoded API key that will not
  match your server.

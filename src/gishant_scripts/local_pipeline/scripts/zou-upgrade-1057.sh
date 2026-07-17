#!/bin/bash
# Migrate the local Kitsu (zou) database from pre-squash 0.20.51 (rev d80f02824047) to
# 1.0.57 (rev c7d3f9b2a1e4), the direct two-phase way, snapshotting first.
#
# cgwire's own `zou upgrade-db` cannot do this: revision a1b2c3d4e5f6 is both the legacy
# head and the new-tree base, so its combined alembic config sees multiple heads and
# `upgrade head` aborts. This script drives the two trees with separate configs via
# zou_upgrade_1057.py (which runs inside the zou 1.0.57 container).
#
#   scripts/zou-upgrade-1057.sh              # snapshot + migrate the live zoudb
#   DB_NAME=zoudb_rnd scripts/zou-upgrade-1057.sh   # target a throwaway copy
#
# Idempotent: re-running when already at head is a no-op. Bails loudly on any single
# migration failure - never leaves work behind a silent `|| true`.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

KITSU_COMPOSE_DIR="${KITSU_COMPOSE_DIR:-$HERE/../kitsu-server}"
DB_CONTAINER="${DB_CONTAINER:-db}"
DB_SERVICE="${DB_SERVICE:-zou}"
DB_USER="${DB_USER:-zou}"
DB_NAME="${DB_NAME:-zoudb}"
BACKUP_DIR="${BACKUP_DIR:-/home/gisi/dev/backups}"
MIGRATOR_PY="$HERE/zou_upgrade_1057.py"

HEAD_REV="c7d3f9b2a1e4"

NC='\033[0m'; RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; BOLD='\033[1m'
log()     { echo -e "  ${BLUE}i${NC}  $*"; }
success() { echo -e "  ${GREEN}✓${NC}  ${GREEN}$*${NC}"; }
error()   { echo -e "  ${RED}✗${NC}  ${RED}$*${NC}" >&2; }
header()  { echo -e "\n${BOLD}=== $* ===${NC}"; }

[[ -f "$MIGRATOR_PY" ]] || { error "missing: $MIGRATOR_PY"; exit 1; }
[[ -d "$KITSU_COMPOSE_DIR" ]] || { error "missing compose dir: $KITSU_COMPOSE_DIR"; exit 1; }

db_psql() { docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$1" -t -A "${@:2}"; }

header "zou DB migration 0.20.51 -> 1.0.57 (db=$DB_NAME)"

# ── Current revision ───────────────────────────────────────────────────────────
CURRENT_REV="$(db_psql "$DB_NAME" -c "SELECT version_num FROM alembic_version;" 2>/dev/null | head -1 || true)"
log "current revision: ${CURRENT_REV:-<none>}"

if [[ "$CURRENT_REV" == "$HEAD_REV" ]]; then
    success "Already at 1.0.57 head ($HEAD_REV) - nothing to do."
    exit 0
fi

# ── Snapshot BEFORE touching the DB (reversible) ───────────────────────────────
mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
SNAPSHOT="$BACKUP_DIR/${DB_NAME}_pre_1057_${TS}.dump"
header "Snapshot"
log "pg_dump $DB_NAME -> $SNAPSHOT"
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc -d "$DB_NAME" -f "/tmp/snap_${TS}.dump"
docker cp "$DB_CONTAINER:/tmp/snap_${TS}.dump" "$SNAPSHOT"
docker exec "$DB_CONTAINER" rm -f "/tmp/snap_${TS}.dump"
SNAP_SIZE="$(du -h "$SNAPSHOT" | cut -f1)"
success "Snapshot written: $SNAPSHOT ($SNAP_SIZE)"
log "restore if needed: docker exec -i $DB_CONTAINER pg_restore -U $DB_USER -d $DB_NAME -c --no-owner < $SNAPSHOT"

# ── Run the two-phase migrator inside the zou 1.0.57 container ──────────────────
header "Migrate (two-phase, stepwise)"
pushd "$KITSU_COMPOSE_DIR" > /dev/null
if ! docker compose run --rm --no-deps -T -w /app \
        -e DB_DATABASE="$DB_NAME" \
        -v "$MIGRATOR_PY:/tmp/zou_upgrade_1057.py:ro" \
        "$DB_SERVICE" python /tmp/zou_upgrade_1057.py; then
    popd > /dev/null
    error "Migration FAILED. DB left partially migrated; restore from: $SNAPSHOT"
    exit 1
fi
popd > /dev/null

# ── Verify head ────────────────────────────────────────────────────────────────
header "Verify"
FINAL_REV="$(db_psql "$DB_NAME" -c "SELECT version_num FROM alembic_version;" 2>/dev/null | head -1 || true)"
if [[ "$FINAL_REV" != "$HEAD_REV" ]]; then
    error "Expected head $HEAD_REV, got '$FINAL_REV'. Restore from: $SNAPSHOT"
    exit 1
fi
success "Database at 1.0.57 head: $FINAL_REV"
for tbl in person task task_person_link project; do
    cnt="$(db_psql "$DB_NAME" -c "SELECT count(*) FROM $tbl;" 2>/dev/null | head -1 || echo '?')"
    log "rows $tbl: $cnt"
done
success "zou DB migration complete."

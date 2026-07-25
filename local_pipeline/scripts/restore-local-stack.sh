#!/bin/bash
# Restore the local AYON + Kitsu stacks from the hourly prod backups, point the rdo_kitsu
# add-on at the LOCAL Kitsu, start the processor, and verify none of it talks to prod.
#
# One idempotent command for the whole sequence. Safe to re-run: the restore drops and
# recreates both databases, the localize step reuses a still-valid bot token, and
# `compose up -d` converges.
#
#   sudo scripts/restore-local-stack.sh --dry-run   # print the plan, touch nothing
#   sudo scripts/restore-local-stack.sh             # execute
#
# Must run as root: sync-and-restore-databases.sh enforces EUID 0.
#
# Phase order matters. The add-on version check (runbook §0) runs AFTER the restore,
# because the restored production dump is what decides which add-on versions exist.
#
# Cron (12:30 AM daily):
#   30 0 * * * /home/gisi/dev/repos/gishant-scripts/local_pipeline/scripts/restore-local-stack.sh >> /home/gisi/dev/backups/restore-local-stack.log 2>&1
# Install: sudo crontab -e

set -euo pipefail

################################################################################
# Paths (derived from this script's location - never $HOME, which sudo rewrites)
################################################################################

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE="$(cd "$HERE/.." && pwd)"                  # local_pipeline/
GS_ROOT="$(cd "$PIPELINE/.." && pwd)"         # gishant-scripts repo root
REPOS_DIR="$(cd "$GS_ROOT/.." && pwd)"              # ~/dev/repos (for the external rdo-ayon-kitsu)

RESTORE_SCRIPT="$HERE/sync-and-restore-databases.sh"
PROCESSOR_DIR="$PIPELINE/processor"
UP_SCRIPT="$PROCESSOR_DIR/up-local-stack.sh"
INSTALL_SCRIPT="$HERE/install_rdo_kitsu.py"
LOCALIZE_SCRIPT="$HERE/localize_kitsu_addon.py"
OVERRIDE_COMPOSE="$PROCESSOR_DIR/docker-compose.local.yml"
AYON_ENV="$PIPELINE/ayon-server/.env"
RDO_ENV="${RDO_ENV:-/home/gisi/.rdo/.env}"
KITSU_COMPOSE_DIR="$PIPELINE/kitsu-server"
VENV_PY="$PIPELINE/.venv/bin/python"          # local_pipeline owns its venv: (cd local_pipeline && uv sync)
PROCESSOR_COMPOSE="${PROCESSOR_COMPOSE:-$REPOS_DIR/rdo-ayon-kitsu/services/processor/docker-compose.yml}"

COMPOSE_PROJECT="rdo-kitsu-processor-local"
STAGING_DIR="/home/gisi/dev/backups"

################################################################################
# Defaults / flags
################################################################################

DRY_RUN=0
SKIP_RESTORE=0
ADDON_VERSION="0.3.3"
ADDON_NAME="rdo_kitsu"
# Host LAN IP, not host.docker.internal: this must resolve from BOTH the processor
# container and the ayon-server container (which declares no extra_hosts).
KITSU_URL="http://10.1.69.24:8090"
AYON_URL="http://10.1.69.24:5000"
KITSU_HEALTH_URL="http://10.1.69.24:5005/status"
AYON_READY_TIMEOUT=300

usage() {
    cat <<USAGE
Usage: sudo $0 [options]

  --dry-run             Print the plan and run read-only checks. No side effects.
  --skip-restore        Skip phase 1 (databases already restored).
  --addon-version VER   rdo_kitsu version to configure (default: $ADDON_VERSION).
  --kitsu-url URL       Local Kitsu URL (default: $KITSU_URL).
  --ayon-url URL        Local AYON URL (default: $AYON_URL).
  -h, --help            Show this help.

Phases: 1 restore DBs -> 2 preflight add-on version -> 3 localize -> 4 processor up
        -> 5 full sync -> 6 verify
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)        DRY_RUN=1; shift ;;
        --skip-restore)   SKIP_RESTORE=1; shift ;;
        --addon-version)  ADDON_VERSION="$2"; shift 2 ;;
        --kitsu-url)      KITSU_URL="$2"; shift 2 ;;
        --ayon-url)       AYON_URL="$2"; shift 2 ;;
        -h|--help)        usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

################################################################################
# Output helpers
################################################################################

NC='\033[0m'; RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'

header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${NC}"; }
log()     { echo -e "  ${BLUE}i${NC}  $*"; }
success() { echo -e "  ${GREEN}✓${NC}  ${GREEN}$*${NC}"; }
warning() { echo -e "  ${YELLOW}!${NC}  ${YELLOW}$*${NC}"; }
error()   { echo -e "  ${RED}✗${NC}  ${RED}$*${NC}" >&2; }

# Fail loudly and leave a breadcrumb rather than continuing into a half state.
die() {
    error "$*"
    error "STOPPED at phase ${CURRENT_PHASE:-?}. Nothing further was attempted."
    exit 1
}

CURRENT_PHASE="startup"

# is_local_url <url> - mirrors the guard in localize_kitsu_addon.py
is_local_url() {
    local host
    host="$(printf '%s' "$1" | sed -E 's#^[a-z]+://##i; s#[:/].*$##')"
    [[ "$host" =~ ^(localhost|127\.0\.0\.1|10\.1\.69\.24|host\.docker\.internal)$ ]]
}

read_env_value() {
    local file="$1" key="$2"
    grep -E "^[[:space:]]*${key}=" "$file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'" | xargs || true
}

http_code() { curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$1" 2>/dev/null || echo "000"; }

wait_for_http() {
    local url="$1" timeout="$2" label="$3" waited=0
    log "Waiting for $label ($url), up to ${timeout}s..."
    while [[ $waited -lt $timeout ]]; do
        if [[ "$(http_code "$url")" == "200" ]]; then
            success "$label is up (200) after ${waited}s"
            return 0
        fi
        sleep 5; waited=$((waited + 5))
    done
    return 1
}

compose_processor() {
    docker compose -p "$COMPOSE_PROJECT" \
        -f "$PROCESSOR_COMPOSE" -f "$OVERRIDE_COMPOSE" \
        --env-file "$PROCESSOR_DIR/.env.local" "$@"
}

# ayon_login_token - log in to AYON as the ~/.rdo/.env user (gisi) and print the
# access token. Used as the API key for all AYON calls, so operations run as the real
# user rather than a synthetic service account (which a fresh restore would wipe).
ayon_login_token() {
    # Log in to AYON as the ~/.rdo/.env user and print the access token. Uses requests
    # with a short retry so a transient hiccup during the (single) login does not abort
    # the whole run. A single-quoted heredoc keeps the Python free of shell escaping.
    AYON_URL="$AYON_URL" RDO_ENV="$RDO_ENV" "$VENV_PY" - <<'PY' 2>/dev/null || true
import json, os, time, requests
env = {}
for line in open(os.environ["RDO_ENV"]):
    line = line.strip()
    if line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    env[k.strip()] = v.strip().strip("'").strip('"')
payload = {"name": env.get("AYON_USERNAME", ""), "password": env.get("AYON_PASSWORD", "")}
url = os.environ["AYON_URL"] + "/api/auth/login"
for attempt in range(4):
    try:
        r = requests.post(url, json=payload, timeout=15)
        token = r.json().get("token", "") if r.ok else ""
        if token:
            print(token)
            break
    except Exception:
        pass
    time.sleep(2)
PY
}

# installed_addon_versions - print installed versions of $ADDON_NAME, one per line.
installed_addon_versions() {
    curl -s --max-time 15 -H "x-api-key: $AYON_API_KEY" "$AYON_URL/api/addons" \
        | "$VENV_PY" -c "
import sys, json
try:
    addons = json.load(sys.stdin).get('addons', [])
except Exception:
    sys.exit(0)
for a in addons:
    if a.get('name') == '$ADDON_NAME':
        print('\\n'.join(sorted(a.get('versions', {}))))
" || true
}

################################################################################
# Phase 0 - preconditions (no side effects)
################################################################################

CURRENT_PHASE="0 (preconditions)"
header "Phase 0: Preconditions"

# Root is only needed for the restore (reads the root-owned backup mount). --skip-restore
# and --dry-run do not touch it, so they may run as the normal user.
[[ $DRY_RUN -eq 1 || $SKIP_RESTORE -eq 1 || "$EUID" -eq 0 ]] || die "Must run as root for the restore (reads /tech/backups). Use: sudo $0  (or --skip-restore to skip it)."

[[ -x "$VENV_PY" ]] || die "local_pipeline venv missing. Create it: (cd $PIPELINE && uv sync)"

for f in "$RESTORE_SCRIPT" "$UP_SCRIPT" "$INSTALL_SCRIPT" "$LOCALIZE_SCRIPT" "$OVERRIDE_COMPOSE" "$AYON_ENV" "$RDO_ENV" "$PROCESSOR_COMPOSE"; do
    [[ -e "$f" ]] || die "Required file missing: $f"
done
success "All required files present"

docker compose version &>/dev/null || die "docker compose not available"
success "docker compose available"

is_local_url "$AYON_URL"  || die "AYON URL is not local: $AYON_URL"
is_local_url "$KITSU_URL" || die "Kitsu URL is not local: $KITSU_URL"
success "Target URLs are local (AYON $AYON_URL / Kitsu $KITSU_URL)"

AYON_USER="$(read_env_value "$RDO_ENV" "AYON_USERNAME")"
[[ -n "$AYON_USER" && -n "$(read_env_value "$RDO_ENV" "AYON_PASSWORD")" ]] \
    || die "AYON_USERNAME/AYON_PASSWORD not found in $RDO_ENV"
success "AYON login credentials loaded from $RDO_ENV (user: $AYON_USER)"

AVAIL_GB=$(df -BG --output=avail "$STAGING_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')
if [[ -n "$AVAIL_GB" && "$AVAIL_GB" -lt 20 ]]; then
    die "Only ${AVAIL_GB}G free on $STAGING_DIR; need ~20G for staging + temp dump."
fi
success "Disk space OK (${AVAIL_GB:-?}G free on $STAGING_DIR)"

if [[ $DRY_RUN -eq 1 ]]; then
    header "DRY RUN - the plan"
    cat <<PLAN
  1. Restore DBs   : $RESTORE_SCRIPT
                     (drops + recreates AYON and Kitsu databases; pv byte-bar on the AYON .sql.gz)
  2. Add-on+bundle : wait for $AYON_URL/api/info, log in as the $RDO_ENV user, install
                     $ADDON_NAME $ADDON_VERSION if missing, and (re)create a dev bundle by cloning
                     the current staging bundle (owned by that user).
  3. Localize      : localize --apply (writes LOCAL Kitsu server + a fresh bot token to the
                     dev bundle's own settings variant)
  4. Processor up  : $UP_SCRIPT   (regenerates .env.local 0600, refuses non-local AYON)
  5. Full sync     : localize_kitsu_addon --apply --full-sync
  6. Verify        : AYON 200 / Kitsu backend + frontend 200 / containers running / settings LOCAL / no prod host

  Nothing was changed.
PLAN
    exit 0
fi

################################################################################
# Phase 1 - restore both databases
################################################################################

CURRENT_PHASE="1 (restore)"
if [[ $SKIP_RESTORE -eq 1 ]]; then
    header "Phase 1: Restore databases (SKIPPED via --skip-restore)"
    warning "Skipping restore; assuming databases are already restored."
else
    header "Phase 1: Restore databases"
    log "Running $RESTORE_SCRIPT (this is the long one; AYON dump is ~4GB gzipped)"
    "$RESTORE_SCRIPT" || die "Database restore failed."
    success "Databases restored"

    # The restore script swallows `zou upgrade-db` failures with `|| true`, so check the
    # Kitsu schema explicitly rather than trusting the exit code.
    log "Verifying Kitsu schema migration..."
    if (cd "$KITSU_COMPOSE_DIR" && docker compose run --rm zou zou is-db-ready) >/tmp/zou_db_ready.log 2>&1; then
        success "Kitsu schema is at head"
    else
        error "Kitsu schema check failed. Tail of output:"
        tail -15 /tmp/zou_db_ready.log >&2 || true
        die "Kitsu migration/schema is not healthy."
    fi
fi

################################################################################
# Phase 2 - preflight: add-on version present in the RESTORED AYON (runbook 0)
################################################################################

CURRENT_PHASE="2 (preflight add-on version)"
header "Phase 2: Preflight - add-on version in the restored AYON"

wait_for_http "$AYON_URL/api/info" "$AYON_READY_TIMEOUT" "AYON API" \
    || die "AYON API did not come up at $AYON_URL within ${AYON_READY_TIMEOUT}s. Check: docker compose -f $PIPELINE/ayon-server/docker-compose.yml ps"

# Authenticate as the real user (gisi). Done here, after the restore, so the session is
# fresh for the localize/install/verify steps that follow.
AYON_API_KEY="$(ayon_login_token)"
[[ -n "$AYON_API_KEY" ]] || die "AYON login as $AYON_USER failed (check credentials in $RDO_ENV)."
success "Logged in to AYON as $AYON_USER"

INSTALLED="$(installed_addon_versions)"
[[ -n "$INSTALLED" ]] || die "$ADDON_NAME is not installed at all on $AYON_URL (or the API key was rejected)."
log "$ADDON_NAME versions installed: $(printf '%s' "$INSTALLED" | tr '\\n' ' ')"

# Install the add-on if missing and (re)create the dev bundle by cloning the current
# staging bundle. Idempotent: the upload is skipped when $ADDON_VERSION is already present.
# Streamed live (tee) and captured so the dev bundle name can be threaded to the localize
# and processor steps.
log "Ensuring $ADDON_NAME $ADDON_VERSION + dev bundle (clone of the current staging bundle)..."
INSTALL_LOG="$(mktemp)"
AYON_SERVER_URL="$AYON_URL" AYON_API_KEY="$AYON_API_KEY" "$VENV_PY" "$INSTALL_SCRIPT" 2>&1 | tee "$INSTALL_LOG"
install_rc=${PIPESTATUS[0]}
DEV_BUNDLE="$(sed -n 's/^BUNDLE_NAME=//p' "$INSTALL_LOG" | tail -1)"
rm -f "$INSTALL_LOG"
[[ $install_rc -eq 0 ]] || die "rdo_kitsu install / dev bundle creation failed."
[[ -n "$DEV_BUNDLE" ]] || die "could not determine the dev bundle name from the install output."
grep -qxF "$ADDON_VERSION" <<<"$(installed_addon_versions)" \
    || die "$ADDON_NAME $ADDON_VERSION still not installed after install attempt."
success "$ADDON_NAME $ADDON_VERSION installed; dev bundle: $DEV_BUNDLE"

################################################################################
# Phase 3 - localize the add-on to the local Kitsu
################################################################################

CURRENT_PHASE="3 (localize)"
header "Phase 3: Point rdo_kitsu at the local Kitsu"

AYON_API_KEY="$AYON_API_KEY" "$VENV_PY" "$LOCALIZE_SCRIPT" --apply \
    --ayon-url "$AYON_URL" --kitsu-url "$KITSU_URL" --addon-version "$ADDON_VERSION" \
    --variant production --variant "$DEV_BUNDLE" \
    || die "Localize step failed. The add-on may still point at prod - do NOT start the processor."
success "Add-on settings localized"

################################################################################
# Phase 4 - bring the processor up
################################################################################

CURRENT_PHASE="4 (processor up)"
header "Phase 4: Start the processor stack"

PROCESSOR_COMPOSE="$PROCESSOR_COMPOSE" AYON_ENV="$AYON_ENV" AYON_API_KEY="$AYON_API_KEY" "$UP_SCRIPT" \
    || die "Processor stack failed to start."

# up-local-stack.sh runs as root here, so hand .env.local back to the repo owner.
REPO_OWNER="$(stat -c '%U:%G' "$GS_ROOT")"
if [[ -f "$PROCESSOR_DIR/.env.local" ]]; then
    chown "$REPO_OWNER" "$PROCESSOR_DIR/.env.local" || true
    log ".env.local owner set to $REPO_OWNER (0600)"
fi
success "Processor stack started"

################################################################################
# Phase 5 - request a full sync for every paired project
################################################################################

CURRENT_PHASE="5 (full sync)"
header "Phase 5: Request full sync"

AYON_API_KEY="$AYON_API_KEY" "$VENV_PY" "$LOCALIZE_SCRIPT" --apply --full-sync \
    --ayon-url "$AYON_URL" --kitsu-url "$KITSU_URL" --addon-version "$ADDON_VERSION" \
    --variant production --variant "$DEV_BUNDLE" \
    || die "Full sync request failed."
success "Full sync requested"

################################################################################
# Phase 6 - verify
################################################################################

CURRENT_PHASE="6 (verify)"
header "Phase 6: Verify"

VERIFY_FAILED=0

if [[ "$(http_code "$AYON_URL/api/info")" == "200" ]]; then
    success "AYON API responds 200 ($AYON_URL)"
else
    error "AYON API is not responding 200"
    VERIFY_FAILED=1
fi

if [[ "$(http_code "$KITSU_HEALTH_URL")" == "200" ]]; then
    success "Kitsu backend responds 200 ($KITSU_HEALTH_URL)"
else
    error "Kitsu backend is not responding 200"
    VERIFY_FAILED=1
fi

if [[ "$(http_code "$KITSU_URL")" == "200" ]]; then
    success "Kitsu frontend/gateway serving 200 ($KITSU_URL)"
else
    error "Kitsu frontend/gateway is not serving 200 ($KITSU_URL)"
    VERIFY_FAILED=1
fi

# Containers: running and not stuck restarting.
for svc in kafka listener consumer; do
    state="$(compose_processor ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s {print $2}')"
    if [[ "$state" == "running" ]]; then
        success "processor/$svc is running"
    else
        error "processor/$svc state = ${state:-<missing>}"
        VERIFY_FAILED=1
    fi
done

# Settings must read back LOCAL, never prod.
SETTINGS_SERVER="$(curl -s --max-time 15 -H "x-api-key: $AYON_API_KEY" \
    "$AYON_URL/api/addons/$ADDON_NAME/$ADDON_VERSION/settings?variant=production" \
    | "$VENV_PY" -c "import sys,json; print(json.load(sys.stdin).get('server',''))" 2>/dev/null || true)"

if [[ "$SETTINGS_SERVER" == "$KITSU_URL" ]]; then
    success "Add-on settings point LOCAL: server = $SETTINGS_SERVER"
elif is_local_url "$SETTINGS_SERVER"; then
    warning "Add-on server is local but not the expected URL: $SETTINGS_SERVER (wanted $KITSU_URL)"
else
    error "Add-on server is NOT local: ${SETTINGS_SERVER:-<empty>}"
    VERIFY_FAILED=1
fi

# No prod host anywhere in the processor logs.
if compose_processor logs --tail 500 2>/dev/null | grep -qi "redefine\.co"; then
    error "PROD HOST found in processor logs - investigate before using this stack!"
    compose_processor logs --tail 500 2>/dev/null | grep -i "redefine\.co" | head -5 >&2
    VERIFY_FAILED=1
else
    success "No prod host (redefine.co) in processor logs"
fi

if compose_processor logs --tail 200 listener 2>/dev/null | grep -qi "Successfully authenticated as bot"; then
    success "Listener authenticated against local Kitsu"
else
    warning "Listener has not logged bot authentication yet (it may still be starting)"
fi

header "Result"
if [[ $VERIFY_FAILED -ne 0 ]]; then
    die "Verification FAILED - see the errors above. The stack is up but not trusted."
fi

success "Local stack restored, localized, and verified."
echo ""
log "AYON  : $AYON_URL   (also http://10.1.69.24:5000)"
log "Kitsu : $KITSU_URL"
log "Logs  : docker compose -p $COMPOSE_PROJECT -f $PROCESSOR_COMPOSE -f $OVERRIDE_COMPOSE --env-file $PROCESSOR_DIR/.env.local logs -f listener consumer"

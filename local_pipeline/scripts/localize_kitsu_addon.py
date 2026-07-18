"""Point the local rdo_kitsu add-on at the LOCAL Kitsu after a database restore.

The hourly backups are production dumps, so a freshly restored local AYON carries
production's rdo_kitsu studio settings -- meaning a local processor would happily sync
against the production Kitsu. This script rewrites those settings to the local Kitsu and
mints a fresh bot token for it.

It is the step between restoring the databases and starting the processor:

    1. sudo scripts/sync-and-restore-databases.sh
    2. python scripts/localize_kitsu_addon.py --apply                  <-- this script
    3. src/gishant_scripts/ayon-kitsu-processor/up-local-stack.sh

Defaults to a dry run: pass --apply to write. Refuses to touch anything that does not
look local.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import requests
from rich.console import Console

PIPELINE = Path(__file__).resolve().parents[1]   # local_pipeline/
AYON_ENV_FILE = PIPELINE / "ayon-server" / ".env"
KITSU_COMPOSE_DIR = PIPELINE / "kitsu-server"

ADDON_NAME = "rdo_kitsu"
DEFAULT_ADDON_VERSION = "0.3.3"

# The host's LAN IP, not host.docker.internal: this URL is resolved by BOTH the
# processor container (own bridge network) and the ayon-server container, and
# ayon-server's compose service declares no extra_hosts, so host.docker.internal
# would not resolve there. The nginx `kitsu` gateway on :8090 serves /api + /socket.io
# (zou-direct on :5005 is root-only and cannot serve the addon's /api calls).
DEFAULT_KITSU_URL = "http://10.1.69.24:8090"
DEFAULT_AYON_URL = "http://10.1.69.24:5000"

BOT_EMAIL = "ayon-local-sync-bot@redefine.co"
BOT_NAME = "AYON Local Sync Bot"

# Anything outside this set is treated as production and refused.
LOCAL_HOST_PATTERN = re.compile(r"^(localhost|127\.0\.0\.1|10\.1\.69\.24|host\.docker\.internal)$")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")

HTTP_TIMEOUT = 30

console = Console()


class LocalizeError(Exception):
    """Raised when the add-on cannot be localized."""


def _is_local_url(url: str) -> bool:
    """Return True when the URL points at this machine."""
    host = urllib.parse.urlparse(url).hostname or ""
    return bool(LOCAL_HOST_PATTERN.match(host))


def _require_local(url: str, label: str) -> None:
    """Abort unless the URL is local. The guard against ever writing to production."""
    if not _is_local_url(url):
        raise LocalizeError(f"{label} does not look local: {url!r}. Refusing to continue.")


def read_env_value(env_file: Path, key: str) -> str | None:
    """Return a single value from a docker .env file without sourcing it.

    The file holds unrelated secrets, so it is parsed rather than executed.
    """
    if not env_file.is_file():
        return None
    value = None
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, val = line.partition("=")
        if name.strip() == key:
            value = val.strip().strip("\"'")
    return value or None


class AyonClient:
    """Minimal AYON REST client.

    ayon_api exposes getters for add-on settings but no setter, so studio settings are
    written through the documented REST route:
        POST /api/addons/{addon}/{version}/settings?variant=production
    """

    def __init__(self, url: str, api_key: str) -> None:
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        response = self.session.request(method, f"{self.url}{path}", timeout=HTTP_TIMEOUT, **kwargs)
        if response.status_code >= 400:
            raise LocalizeError(f"AYON {method} {path} -> {response.status_code}: {response.text[:400]}")
        return response

    def installed_versions(self, addon_name: str) -> list[str]:
        """Return the add-on versions installed on this server."""
        data = self._request("GET", "/api/addons").json()
        for addon in data.get("addons", []):
            if addon.get("name") == addon_name:
                return sorted(addon.get("versions", {}))
        return []

    def get_studio_settings(self, addon_name: str, version: str, variant: str = "production") -> dict:
        """Return the add-on's studio settings, including any overrides."""
        return self._request(
            "GET", f"/api/addons/{addon_name}/{version}/settings", params={"variant": variant}
        ).json()

    def set_studio_settings(
        self, addon_name: str, version: str, payload: dict, variant: str = "production"
    ) -> None:
        """Write the add-on's studio settings. The payload must be the full settings model."""
        self._request(
            "POST",
            f"/api/addons/{addon_name}/{version}/settings",
            params={"variant": variant},
            data=json.dumps(payload),
        )

    def paired_projects(self, addon_name: str, version: str) -> list[dict]:
        """Return the Kitsu <-> AYON project pairings known to the add-on."""
        return self._request("GET", f"/api/addons/{addon_name}/{version}/pairing").json()

    def request_full_sync(self, addon_name: str, version: str, project_name: str) -> None:
        """Ask the add-on to dispatch a kitsu.sync_request event for one project.

        This is what actually triggers a full sync; the processor's listener enrols on
        the event. There is no STARTUP_FULL_SYNC env var -- the processor reads no such
        setting.
        """
        self._request("POST", f"/api/addons/{addon_name}/{version}/sync/{project_name}")


def kitsu_token_is_valid(kitsu_url: str, token: str) -> bool:
    """Return True when the token still authenticates against the local Kitsu."""
    if not token:
        return False
    try:
        response = requests.get(
            f"{kitsu_url.rstrip('/')}/api/auth/authenticated",
            headers={"Authorization": f"Bearer {token}"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        return False
    return response.status_code == 200


def mint_kitsu_bot_token(compose_dir: Path) -> str:
    """Create a fresh Kitsu bot and return its access token.

    Zou stores only the token's jti, never the token, so an existing bot's token cannot
    be read back. To stay idempotent the bot is deleted first and recreated: the email
    carries a unique constraint (only_one_email_by_person), so creating over an existing
    bot would otherwise fail.
    """
    delete_snippet = (
        "from zou.app import app\n"
        "from zou.app.models.person import Person\n"
        "from zou.app.services import persons_service\n"
        "with app.app_context():\n"
        f"        person = Person.query.filter_by(email={BOT_EMAIL!r}).first()\n"
        "        if person:\n"
        "            persons_service.delete_person(str(person.id))\n"
        "            print('deleted existing bot')\n"
    )
    _run_compose(
        compose_dir,
        ["run", "--rm", "--no-deps", "-e", "MAIL_CHECK_DELIVERABILITY=false",
         "zou", "python", "-c", delete_snippet],
        "delete stale bot",
    )

    result = _run_compose(
        compose_dir,
        ["run", "--rm", "--no-deps", "-e", "MAIL_CHECK_DELIVERABILITY=false",
         "zou", "zou", "create-bot", "--email", BOT_EMAIL, "--name", BOT_NAME, "--role", "admin"],
        "create bot",
    )
    # zou create-bot prints the raw JWT; other log lines may share stdout.
    matches = JWT_PATTERN.findall(result.stdout)
    if not matches:
        raise LocalizeError(f"Could not find a token in `zou create-bot` output:\n{result.stdout[-800:]}")
    return matches[-1]


def _run_compose(compose_dir: Path, args: list[str], label: str) -> subprocess.CompletedProcess[str]:
    """Run a docker compose command in the Kitsu stack directory."""
    command = ["docker", "compose", *args]
    result = subprocess.run(command, cwd=compose_dir, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise LocalizeError(f"{label} failed ({result.returncode}):\n{result.stderr[-800:]}")
    return result


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="localize_kitsu_addon",
        description="Point the local rdo_kitsu add-on at the local Kitsu after a restore.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default is a dry run).")
    parser.add_argument("--ayon-url", default=None, help=f"Local AYON URL (default: {DEFAULT_AYON_URL}).")
    parser.add_argument("--kitsu-url", default=DEFAULT_KITSU_URL, help=f"Local Kitsu URL (default: {DEFAULT_KITSU_URL}).")
    parser.add_argument("--addon-version", default=DEFAULT_ADDON_VERSION, help="rdo_kitsu version to configure.")
    parser.add_argument(
        "--variant", action="append", dest="variants",
        help="Settings variant to write; repeatable. Default: production. "
        "production is mandatory (the addon server-side reads it); pass the dev "
        "bundle name too to also populate the launcher's variant.",
    )
    parser.add_argument("--force-token", action="store_true", help="Mint a new bot token even if the current one works.")
    parser.add_argument("--full-sync", action="store_true", help="Request a full sync for every paired project.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the localize step. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    dry_run = not args.apply

    # Deliberately NOT read from ayon-server/.env: AYON_SERVER_URL there is the
    # container-internal URL (http://server:5000) used by the worker, which does not
    # resolve from the host. Only the API key is taken from that file.
    ayon_url = args.ayon_url or DEFAULT_AYON_URL
    # Prefer an injected key (the orchestrator passes gisi's login token); fall back
    # to ayon-server/.env for standalone use.
    api_key = os.environ.get("AYON_API_KEY") or read_env_value(AYON_ENV_FILE, "AYON_API_KEY")
    if not api_key:
        console.print(f"[red]AYON_API_KEY not found in {AYON_ENV_FILE}[/red]")
        return 1

    try:
        # Never write to anything that is not this machine.
        _require_local(ayon_url, "AYON URL")
        _require_local(args.kitsu_url, "Kitsu URL")

        if dry_run:
            console.print("[yellow]DRY RUN[/yellow] - no changes will be made. Pass --apply to write.\n")

        ayon = AyonClient(ayon_url, api_key)
        console.print(f"AYON        : {ayon_url}")
        console.print(f"Kitsu       : {args.kitsu_url}")

        versions = ayon.installed_versions(ADDON_NAME)
        if args.addon_version not in versions:
            raise LocalizeError(
                f"{ADDON_NAME} {args.addon_version} is not installed on {ayon_url}. "
                f"Installed: {versions or 'none'}. Pass --addon-version to pick one."
            )
        console.print(f"Add-on      : {ADDON_NAME} {args.addon_version} (installed: {', '.join(versions)})\n")

        variants = args.variants or ["production"]
        # 'production' is mandatory: the addon's server-side endpoints (/pairing, /sync)
        # always read it. Extra variants (e.g. the dev bundle name) mirror the same values
        # so the launcher's own settings screen shows local too. The primary variant (first)
        # drives the token-reuse check; all variants get the same minted token.
        primary = ayon.get_studio_settings(ADDON_NAME, args.addon_version, variants[0])
        current_server = primary.get("server", "")
        current_token = primary.get("kitsu_api_key", "")
        console.print(f"variants           : {', '.join(variants)}")
        console.print(f"current server     : {current_server or '<unset>'} (variant {variants[0]})")
        console.print(f"current token      : {'<set>' if current_token else '<unset>'}")
        if current_server and not _is_local_url(current_server):
            console.print(f"[yellow]-> currently NON-LOCAL {current_server} (restored prod settings)[/yellow]")

        reuse = (
            not args.force_token
            and current_server == args.kitsu_url
            and kitsu_token_is_valid(args.kitsu_url, current_token)
        )

        if reuse and not args.full_sync:
            all_local = all(
                ayon.get_studio_settings(ADDON_NAME, args.addon_version, v).get("server") == args.kitsu_url
                for v in variants
            )
            if all_local:
                console.print("\n[green]Nothing to do (all variants already local).[/green]")
                return 0

        if dry_run:
            console.print("\n[yellow]Would apply to variants:[/yellow] " + ", ".join(variants))
            console.print(f"  server        -> {args.kitsu_url}")
            console.print(f"  kitsu_api_key -> {'<unchanged>' if reuse else '<new bot token>'}")
            if args.full_sync:
                console.print("  full sync     -> every paired project")
            return 0

        if reuse:
            token = current_token
        else:
            console.print(f"\nMinting Kitsu bot token ({BOT_EMAIL})...")
            token = mint_kitsu_bot_token(KITSU_COMPOSE_DIR)
            console.print("[green]Bot token minted[/green]")

        for variant in variants:
            base = ayon.get_studio_settings(ADDON_NAME, args.addon_version, variant)
            payload = dict(base)
            payload["server"] = args.kitsu_url
            payload["kitsu_api_key"] = token
            ayon.set_studio_settings(ADDON_NAME, args.addon_version, payload, variant)
            verify = ayon.get_studio_settings(ADDON_NAME, args.addon_version, variant)
            if verify.get("server") != args.kitsu_url or not verify.get("kitsu_api_key"):
                raise LocalizeError(f"Verification failed for variant {variant}: server is {verify.get('server')!r}.")
            console.print(f"[green]Verified [{variant}]: server = {verify['server']}, token set[/green]")

        if args.full_sync:
            pairings = ayon.paired_projects(ADDON_NAME, args.addon_version)
            if not pairings:
                console.print("[yellow]No paired projects; nothing to sync.[/yellow]")
            for pair in pairings:
                project = pair.get("ayonProjectName")
                if not project:
                    continue
                ayon.request_full_sync(ADDON_NAME, args.addon_version, project)
                console.print(f"  sync requested: {project}")

    except LocalizeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    console.print("\n[green]Done. Start the processor with ayon-kitsu-processor/up-local-stack.sh[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

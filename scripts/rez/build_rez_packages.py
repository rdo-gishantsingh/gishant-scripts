from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_REPOS_ROOT = Path("/tech/users/gisi/dev/repos")
DEFAULT_LIST_FILE = Path(__file__).with_name("rez_repos.txt")
DEFAULT_BUILD_CMD = ["rez-build", "-ci"]


def _parse_repo_list(list_file: Path) -> list[str]:
    repos: list[str] = []
    for line in list_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        repos.append(stripped)
    return repos


def _build_repo(repo_path: Path, build_cmd: list[str], dry_run: bool) -> bool:
    if dry_run:
        print(f"[DRY RUN] {' '.join(build_cmd)} (cwd={repo_path})")
        return True
    result = subprocess.run(build_cmd, cwd=repo_path, check=False)
    return result.returncode == 0


def run(
    list_file: Path,
    repos_root: Path,
    build_cmd: list[str],
    dry_run: bool,
) -> int:
    if not list_file.exists():
        print(f"List file not found: {list_file}", file=sys.stderr)
        return 2

    repos = _parse_repo_list(list_file)
    if not repos:
        print("No repos to build (list is empty after filtering).")
        return 0

    built: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for repo_name in repos:
        repo_path = repos_root / repo_name
        if not repo_path.exists():
            skipped.append(f"{repo_name} (missing)")
            continue
        if not (repo_path / "package.py").exists():
            skipped.append(f"{repo_name} (no package.py)")
            continue

        print(f"Building {repo_name}...")
        if _build_repo(repo_path, build_cmd, dry_run):
            built.append(repo_name)
        else:
            failed.append(repo_name)

    print("\nSummary")
    print("-" * 40)
    print(f"Built:   {len(built)}")
    print(f"Failed:  {len(failed)}")
    print(f"Skipped: {len(skipped)}")
    if failed:
        print("\nFailed repos:")
        for repo_name in failed:
            print(f"- {repo_name}")
    if skipped:
        print("\nSkipped repos:")
        for entry in skipped:
            print(f"- {entry}")

    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build rez packages from a repo list.")
    parser.add_argument(
        "--list-file",
        type=Path,
        default=DEFAULT_LIST_FILE,
        help="Path to repo list file (one repo per line).",
    )
    parser.add_argument(
        "--repos-root",
        type=Path,
        default=DEFAULT_REPOS_ROOT,
        help="Root directory containing all repos.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run(
        list_file=args.list_file,
        repos_root=args.repos_root,
        build_cmd=DEFAULT_BUILD_CMD,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

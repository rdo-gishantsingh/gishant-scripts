"""RDO Logging showcase — run to demonstrate all logging capabilities.

Run from repo root:
    uv run python scripts/showcase.py
    # or: rez env rdo_logging -- python scripts/showcase.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Optional


# Ensure package is importable when run directly (e.g. python scripts/showcase.py)
# Skip when already importable (e.g. uv run, rez env, or installed package).
def _ensure_importable() -> None:
    try:
        import rdo_logging  # noqa: F401
    except ModuleNotFoundError:
        _repo_root = Path(__file__).resolve().parent.parent
        _python_src = _repo_root / "python"
        if _python_src.exists():
            sys.path.insert(0, str(_python_src))


_ensure_importable()

from rdo_logging import (
    bind_context,
    clear_context,
    configure,
    get_logger,
    reset,
    unbind_context,
    update_progress,
)


def _print_header(text: str) -> None:
    """Print a section header (flushed so it appears before log output)."""
    print(f"\n{'─' * 60}", flush=True)
    print(f"  {text}", flush=True)
    print("─" * 60, flush=True)


def run_showcase(
    *,
    debug: bool = True,
    mode: str = "rich",
    progress_callback: Optional[Callable[[int, str], None]] = None,
    delay_seconds: float = 0,
) -> None:
    """Execute the full logging showcase."""
    configure(debug=debug, mode=mode, progress_callback=progress_callback)
    log = get_logger("showcase")

    # 1. Log levels
    _print_header("1. Log levels (debug, info, warning, error)")
    log.debug("debug message", detail="verbose detail")
    log.info("info message", action="started")
    log.warning("warning message", code="W01")
    log.error("error message", code="E01")
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    # 2. Structured data
    _print_header("2. Structured key-value logging")
    log.info(
        "processing started",
        file_count=42,
        format="exr",
        path="/jobs/shot_001",
    )
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    # 3. Logger binding (per-logger context)
    _print_header("3. Logger binding (log.bind)")
    bound_log = log.bind(task_id="abc-123", user="alice")
    bound_log.info("step 1 complete")
    bound_log.info("step 2 complete")
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    # 4. Context variables (request-scoped, visible to all loggers)
    _print_header("4. Context variables (bind_context / clear_context)")
    clear_context()
    bind_context(request_id="req-456", env="demo")
    log_a = get_logger("module_a")
    log_b = get_logger("module_b")
    log_a.info("from module_a")
    log_b.info("from module_b")
    unbind_context("env")
    get_logger("module_c").info("after unbind env")
    clear_context()
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    # 5. Exception logging
    _print_header("5. Exception logging (log.exception)")
    try:
        raise ValueError("simulated error for demo")
    except ValueError:
        log.exception("caught exception", component="showcase")
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    # 6. Progress callback (if provided)
    if progress_callback:
        _print_header("6. Progress updates (update_progress)")
        for pct, msg in [(25, "Loading..."), (50, "Processing..."), (100, "Done")]:
            update_progress(pct, msg)
            log.info("progress", pct=pct, status=msg)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    # 7. Reset and reconfigure (e.g. for tests)
    _print_header("7. Reset (reset + reconfigure)")
    reset()
    configure(debug=False)
    get_logger("post_reset").info("fresh config", level="INFO only")
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    print(f"\n{'─' * 60}", flush=True)
    print("  Showcase complete.", flush=True)
    print("─" * 60 + "\n", flush=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="RDO Logging showcase")
    parser.add_argument(
        "--mode",
        choices=["rich", "plain", "json"],
        default="rich",
        help="Console renderer (default: rich)",
    )
    parser.add_argument(
        "--with-progress",
        action="store_true",
        help="Demo update_progress() with a print callback",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        metavar="SECS",
        help="Pause SECS seconds after each section (e.g. 3 for recording)",
    )
    args = parser.parse_args()

    cmd_parts = ["uv run python scripts/showcase.py"]
    if args.mode != "rich":
        cmd_parts.append(f"--mode {args.mode}")
    if args.with_progress:
        cmd_parts.append("--with-progress")
    if args.delay > 0:
        cmd_parts.append(f"--delay {args.delay}")
    cmd = " ".join(cmd_parts)

    print("\n" + "=" * 60, flush=True)
    print("  RDO Logging Showcase", flush=True)
    print("=" * 60, flush=True)
    print(f"\n  Command:  {cmd}", flush=True)
    print("\n  (Run from repo root)", flush=True)
    print(flush=True)

    def _progress_demo(pct: int, msg: str) -> None:
        print(f"  [PROGRESS] {pct}% — {msg}")

    progress_cb: Optional[Callable[[int, str], None]] = (
        _progress_demo if args.with_progress else None
    )

    run_showcase(
        debug=True,
        mode=args.mode,
        progress_callback=progress_cb,
        delay_seconds=args.delay,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

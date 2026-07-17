"""Two-phase direct migration of a pre-squash zou DB (0.20.51) to 1.0.57.

Runs INSIDE the zou 1.0.57 container. Idempotent and stepwise: applies one migration
at a time and aborts on the first failure (no silent `|| true`).

Why two phases: revision a1b2c3d4e5f6 is BOTH the legacy-tree head and the new-tree base
(down_revision=None). cgwire's `zou upgrade-db` loads both trees at once, so `upgrade head`
sees multiple heads and can't resolve. Splitting the configs removes the ambiguity:

  Phase 1  legacy-only config (version_locations = versions/legacy):  <cur> -> a1b2c3d4e5f6
  Phase 2  default config     (version_locations = versions):         a1b2c3d4e5f6 -> c7d3f9b2a1e4

Exit 0 on success (including "already at head"), 1 on any migration failure.
"""
import os
import sys
import traceback

sys.path.insert(0, "/app")

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from zou.cli import _get_alembic_config, _get_migrations_path

SQUASH = "a1b2c3d4e5f6"   # legacy head == new-tree base
HEAD = "c7d3f9b2a1e4"     # true 1.0.57 head

new_cfg = _get_alembic_config()
url = new_cfg.get_main_option("sqlalchemy.url")
engine = create_engine(url)

mp = _get_migrations_path()
legacy_cfg = Config(os.path.join(mp, "alembic.ini"))
legacy_cfg.set_main_option("script_location", mp)
legacy_cfg.set_main_option("version_locations", os.path.join(mp, "versions", "legacy"))
legacy_cfg.set_main_option("sqlalchemy.url", url)


def current_rev():
    with engine.connect() as conn:
        try:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            return None


def upgrade_stepwise(cfg, target, base, label):
    """Apply base->target one revision at a time. base=None walks from the tree root."""
    script = ScriptDirectory.from_config(cfg)
    path = [r.revision for r in script.iterate_revisions(target, base)][::-1]
    if not path:
        print(f"  {label}: already at/past {target}, nothing to apply")
        return
    print(f"  {label}: {len(path)} migration(s) {base or 'base'} -> {target}")
    for i, rev in enumerate(path, 1):
        doc = script.get_revision(rev).doc
        try:
            command.upgrade(cfg, rev)
            print(f"    [{i:2d}/{len(path)}] OK   {rev}  {doc}")
        except Exception:
            print(f"    [{i:2d}/{len(path)}] FAIL {rev}  {doc}")
            traceback.print_exc()
            sys.exit(1)


def main():
    cur = current_rev()
    print(f"current revision: {cur}")

    if cur == HEAD:
        print("Already at 1.0.57 head c7d3f9b2a1e4 - nothing to do.")
        return

    new_known = {r.revision for r in ScriptDirectory.from_config(new_cfg).walk_revisions()}

    if cur in new_known:
        # Somewhere inside the post-squash tree already: only phase 2 remains.
        print("Revision is in the post-squash tree; running phase 2 only.")
        upgrade_stepwise(new_cfg, HEAD, cur, "PHASE 2 (post-squash)")
    else:
        # Legacy (pre-squash) revision: phase 1 then phase 2.
        upgrade_stepwise(legacy_cfg, SQUASH, cur, "PHASE 1 (legacy tail)")
        upgrade_stepwise(new_cfg, HEAD, SQUASH, "PHASE 2 (post-squash)")

    final = current_rev()
    print(f"final revision: {final}")
    if final != HEAD:
        print(f"ERROR: expected {HEAD}, got {final}")
        sys.exit(1)
    print("Migration complete: at 1.0.57 head c7d3f9b2a1e4.")


if __name__ == "__main__":
    main()

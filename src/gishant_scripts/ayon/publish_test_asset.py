"""Publish a test movie asset to AYON with Kitsu linking (Bollywoof/test episode only).

Safeguards restrict execution to project Bollywoof and episode "test" only.
Used for validating USER-319 and PIPE-523 (AYON-Kitsu version linking).

Run:
    publish-test-asset [--folder-path PATH] [--task NAME] [--file PATH]
"""

from __future__ import annotations

import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

# Support rdo-core wheels that install modules under site-packages/python/.
for _site_pkg in site.getsitepackages():
    _python_subdir = Path(_site_pkg) / "python"
    if _python_subdir.is_dir() and str(_python_subdir) not in sys.path:
        sys.path.insert(0, str(_python_subdir))

import gazu  # noqa: E402
import typer  # noqa: E402
from rdo_ayon_utils import (  # noqa: E402
    build_ayon_linking_data,
    fill_template,
    get_product_id,
    get_project_root,
    get_project_template,
    get_task_by_name,
    get_version_lineage,
    update_version_ayon_linking,
)
from rdo_kitsu_utils import kitsu_utils  # noqa: E402
from rdo_pms_bridge import pms_bridge, version_linking  # noqa: E402

# =============================================================================
# SAFEGUARDS (hardcoded)
# =============================================================================

PROJECT_ALLOWED = "Bollywoof"
EPISODE_NAME_ALLOWED = "test"


def _ensure_in_episode(folder_path: str, episode_path: str) -> None:
    """Ensure folder path is within the episode. Raises SystemExit if not."""
    ep = episode_path.rstrip("/")
    if not ep:
        ep = episode_path
    target = folder_path.rstrip("/") or folder_path
    if target != ep and not target.startswith(ep + "/"):
        raise SystemExit(
            f"SAFEGUARD: Folder path '{folder_path}' is outside episode '{episode_path}'. "
            f"Only paths under {episode_path} are allowed."
        )


def _resolve_episode_folder(conn, project_name: str):
    """Resolve the episode folder named EPISODE_NAME_ALLOWED. Raises if not found."""
    # Try /episodes/test first (canonical episode path)
    episode_path = f"/episodes/{EPISODE_NAME_ALLOWED}"
    folder = conn.get_folder_by_path(project_name, episode_path)
    if folder and folder.get("folderType") == "Episode":
        return folder

    # Fallback: get_folders and prefer folderType "Episode"
    folders = list(conn.get_folders(project_name, folder_names=[EPISODE_NAME_ALLOWED]))
    episode_folder = next(
        (f for f in folders if f.get("folderType") == "Episode"),
        None,
    )
    if episode_folder:
        return episode_folder

    # Last resort: first match by path /episodes/test
    for f in folders:
        if f.get("path", "").startswith("/episodes/"):
            return f

    if folders:
        return folders[0]

    raise SystemExit(
        f"SAFEGUARD: Episode '{EPISODE_NAME_ALLOWED}' not found in project {project_name}. "
        "Cannot proceed."
    )


def _resolve_target_folder(conn, project_name: str, folder_path: str, episode_folder: dict) -> dict:
    """Resolve target folder and ensure it is within the episode."""
    folder = conn.get_folder_by_path(project_name, folder_path)
    if not folder:
        raise SystemExit(f"Folder not found: {folder_path}")

    ep_path = episode_folder.get("path", "")
    _ensure_in_episode(folder.get("path", ""), ep_path)
    return folder


def _get_task_with_kitsu_link(conn, project_name: str, folder_id: str, task_name: str | None) -> tuple[dict, dict]:
    """Get AYON task and corresponding Kitsu task. Prefer task with kitsuId."""
    tasks = list(conn.get_tasks(project_name, folder_ids=[folder_id]))
    if not tasks:
        raise SystemExit("No tasks found for this folder.")

    if task_name:
        a_task = get_task_by_name(conn, project_name, folder_id, task_name)
        if not a_task:
            raise SystemExit(f"Task '{task_name}' not found.")
    else:
        a_task = next((t for t in tasks if t.get("data", {}).get("kitsuId")), None)
        if not a_task:
            a_task = tasks[0]

    kitsu_id = a_task.get("data", {}).get("kitsuId")
    if not kitsu_id:
        raise SystemExit(
            f"Task '{a_task.get('name')}' has no Kitsu link (data.kitsuId). "
            "Kitsu upload requires a linked task."
        )

    try:
        k_task = gazu.task.get_task(kitsu_id)
    except gazu.exception.RouteNotFoundException:
        raise SystemExit(f"Kitsu task {kitsu_id} not found.") from None

    return a_task, k_task


def _generate_placeholder_mov() -> Path:
    """Generate a 1-frame black mov. Uses ffmpeg if in PATH, else imageio."""
    out = Path(tempfile.gettempdir()) / "publish_test_asset_placeholder.mp4"

    if shutil.which("ffmpeg"):
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=1280x720:d=1",
            "-t", "0.04",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not out.exists():
            raise SystemExit(f"ffmpeg failed: {result.stderr or result.stdout}")
        return out

    try:
        import numpy as np
        import imageio
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        writer = imageio.get_writer(str(out), fps=24)
        writer.append_data(frame)
        writer.close()
        if not out.exists():
            raise SystemExit("imageio failed to create placeholder")
        return out
    except ImportError as e:
        raise SystemExit(
            "Neither ffmpeg nor imageio available. Install ffmpeg or "
            "provide --file with a video path."
        ) from e


def _publish_and_link(
    conn,
    project_name: str,
    folder_entity: dict,
    a_task: dict,
    k_task: dict,
    file_path: Path,
) -> tuple[str, int, str | None]:
    """Publish movie to AYON and Kitsu, store linking data. Returns (version_id, version_num, kitsu_revision_id)."""
    product_name = f"movie{a_task['name'].capitalize()}Main"
    product_type = "movie"

    template = get_project_template(conn, project_name, "publish", "default")
    template_path = f"{template['directory']}/{template['file']}"
    work_root = get_project_root(project_name, conn)
    if not work_root:
        raise SystemExit("Could not get project root.")

    hierarchy_parts = folder_entity.get("path", "").strip("/").split("/")
    hierarchy = "/".join(hierarchy_parts[:-1]) if len(hierarchy_parts) > 1 else ""
    folder_name = hierarchy_parts[-1] if hierarchy_parts else folder_entity.get("label", "unknown")

    version_num = kitsu_utils.get_next_available_revision_number(k_task)
    template_values = {
        "root": {"work": work_root},
        "project": {"name": project_name, "code": project_name},
        "hierarchy": hierarchy,
        "folder": {"name": folder_name},
        "@version": f"v{version_num:03d}",
        "product": {"type": product_type, "name": product_name},
        "ext": file_path.suffix.lstrip("."),
    }

    publish_path = Path(fill_template(template_path, template_values))
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, publish_path)

    k_comment = None
    k_preview = None
    try:
        task_status = gazu.task.get_task_status_by_short_name("wfr")
    except Exception:
        task_status = None

    if task_status:
        k_comment, k_preview = gazu.task.publish_preview(
            k_task,
            task_status,
            comment="Created by publish-test-asset (Bollywoof/test).",
            preview_file_path=str(publish_path),
            revision=version_num,
            set_thumbnail=True,
        )
        if k_preview:
            gazu.files.update_preview(k_preview, {"path": str(publish_path)})

    a_product_id = get_product_id(
        conn,
        project_name,
        folder_entity["id"],
        product_name,
        product_type,
    )
    if not a_product_id:
        raise SystemExit("Failed to get or create product.")

    a_version_id = conn.create_version(
        project_name=project_name,
        version=version_num,
        product_id=a_product_id,
        task_id=a_task["id"],
        data={},
    )

    ayon_linking_data = build_ayon_linking_data(
        project_name=project_name,
        version_entity={"id": a_version_id, "version": version_num},
        source_version_id=None,
        folder_entity=folder_entity,
        product_entity={"name": product_name, "productType": product_type},
    )
    update_version_ayon_linking(
        con=conn,
        project_name=project_name,
        version_id=a_version_id,
        linking_data=ayon_linking_data,
    )

    kitsu_revision_id = k_preview["id"] if k_preview else None
    if k_preview or k_comment:
        kitsu_linking_data = version_linking.build_kitsu_linking_data(
            kitsu_revision_id=kitsu_revision_id,
            additional_data={"kitsu_comment_id": k_comment["id"]} if k_comment else None,
        )
        version_linking.update_version_with_kitsu_linking(
            ayon_connection=conn,
            ayon_project_name=project_name,
            ayon_version_id=a_version_id,
            linking_data=kitsu_linking_data,
        )

    conn.create_representation(
        project_name=project_name,
        name=publish_path.stem,
        version_id=a_version_id,
        attrib={
            "path": str(publish_path),
            "template": template_path,
        },
    )

    return a_version_id, version_num, kitsu_revision_id


def cli(
    folder_path: str | None = typer.Option(
        None,
        "--folder-path",
        "-f",
        help="AYON folder path (must be under episode 'test'). Default: episode itself.",
    ),
    task: str | None = typer.Option(
        None,
        "--task",
        "-t",
        help="Task name (default: first task with Kitsu link).",
    ),
    file_path: str | None = typer.Option(
        None,
        "--file",
        help="Video file path (default: generate 1-frame black placeholder).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Only resolve context and validate; do not publish.",
    ),
) -> None:
    """Publish a test movie asset to AYON in Bollywoof/test with Kitsu linking.

    Safeguards: Only project Bollywoof and episode 'test' are allowed.
    """
    project_name = PROJECT_ALLOWED

    typer.echo("Connecting to AYON and Kitsu...")
    try:
        conn, _k_user = pms_bridge.set_connection()
    except (ValueError, Exception) as e:
        typer.echo(f"Connection failed: {e}", err=True)
        raise typer.Exit(1) from e

    typer.echo(f"Resolving episode '{EPISODE_NAME_ALLOWED}'...")
    episode_folder = _resolve_episode_folder(conn, project_name)
    episode_path = episode_folder.get("path", "")
    typer.echo(f"  Episode path: {episode_path}")

    target_path = folder_path or episode_path
    typer.echo(f"Resolving target folder: {target_path}")
    target_folder = _resolve_target_folder(conn, project_name, target_path, episode_folder)
    if not target_folder.get("data", {}).get("kitsuId"):
        typer.echo(
            "WARNING: Folder has no kitsuId. Kitsu upload may fail.",
            err=True,
        )

    typer.echo("Resolving task...")
    a_task, k_task = _get_task_with_kitsu_link(
        conn, project_name, target_folder["id"], task
    )
    typer.echo(f"  AYON task: {a_task['name']}, Kitsu task: {k_task.get('id')}")

    if dry_run:
        typer.echo("Dry run: context resolved. Exiting without publish.")
        return

    if file_path:
        path = Path(file_path)
        if not path.exists():
            typer.echo(f"File not found: {path}", err=True)
            raise typer.Exit(1)
    else:
        typer.echo("Generating placeholder video (ffmpeg)...")
        path = _generate_placeholder_mov()
        typer.echo(f"  Created: {path}")

    typer.echo("Publishing to AYON and Kitsu...")
    try:
        version_id, version_num, kitsu_rev_id = _publish_and_link(
            conn, project_name, target_folder, a_task, k_task, path
        )
    except Exception as e:
        typer.echo(f"Publish failed: {e}", err=True)
        raise typer.Exit(1) from e

    typer.echo("\n" + "=" * 60)
    typer.echo("PUBLISH COMPLETE")
    typer.echo("=" * 60)
    typer.echo(f"Version ID:    {version_id}")
    typer.echo(f"Version:       v{version_num:03d}")
    typer.echo(f"Kitsu rev ID:  {kitsu_rev_id or '(not uploaded)'}")

    version_entity = conn.get_version_by_id(project_name, version_id)
    ayon_link = version_entity.get("data", {}).get("ayon_linking", {})
    kitsu_link = version_entity.get("data", {}).get("kitsu_linking", {})

    typer.echo("\nayon_linking:")
    for k, v in ayon_link.items():
        typer.echo(f"  {k}: {v}")
    typer.echo("kitsu_linking:")
    for k, v in kitsu_link.items():
        typer.echo(f"  {k}: {v}")

    if kitsu_rev_id:
        found = version_linking.find_version_by_kitsu_revision(
            conn, project_name, kitsu_rev_id
        )
        typer.echo(f"\nVerification (find_version_by_kitsu_revision): {'OK' if found and found.get('id') == version_id else 'MISMATCH'}")

    lineage = get_version_lineage(conn, project_name, version_id)
    typer.echo(f"Lineage chain: {len(lineage)} version(s)")
    for i, v in enumerate(lineage, 1):
        typer.echo(f"  {i}. {v.get('productId', '?')} v{v.get('version', 0):03d}")


def main() -> None:
    """Entry point for the CLI (parses argv and invokes cli)."""
    typer.run(cli)


if __name__ == "__main__":
    main()

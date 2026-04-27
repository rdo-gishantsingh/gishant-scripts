"""Shotgrid task operations — generic, reusable utilities.

All functions are read/write-safe:
- Functions ending in *_dry_run return what *would* change without writing.
- bulk_rename_task_content accepts a dry_run flag; live mode issues sg.batch()
  in chunks of _BATCH_CHUNK_SIZE and self-verifies on completion.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from itertools import islice

logger = logging.getLogger(__name__)

_BATCH_CHUNK_SIZE = 500
_PAGE_SIZE = 500


def _get_project(sg, project_name: str) -> dict:
    project = sg.find_one("Project", [["name", "is", project_name]], ["name", "id", "sg_status"])
    if not project:
        raise ValueError(f"Project '{project_name}' not found in Shotgrid.")
    return project


def _chunked(iterable, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


def get_tasks_by_content(sg, project_name: str, content: str) -> list[dict]:
    """Return all tasks in a project whose content matches exactly (paginated, no cap)."""
    project = _get_project(sg, project_name)
    filters = [
        ["content", "is", content],
        ["project", "is", {"type": "Project", "id": project["id"]}],
    ]
    fields = ["id", "content", "step", "entity", "sg_status_list"]
    all_tasks: list[dict] = []
    page = 1
    while True:
        page_results = sg.find("Task", filters, fields, limit=_PAGE_SIZE, page=page)
        all_tasks.extend(page_results)
        if len(page_results) < _PAGE_SIZE:
            break
        page += 1
    logger.debug(
        "get_tasks_by_content: fetched %d '%s' tasks from '%s' across %d page(s).",
        len(all_tasks), content, project_name, page,
    )
    return all_tasks


def bulk_rename_task_content(
    sg,
    project_name: str,
    from_content: str,
    to_content: str,
    *,
    dry_run: bool = False,
    on_chunk: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Rename all tasks matching from_content to to_content in a Shotgrid project.

    In dry-run mode no writes occur. In live mode batch updates are issued in
    chunks of _BATCH_CHUNK_SIZE (500). on_chunk(updated_so_far, total) is called
    after each chunk — use this to drive a progress bar in the caller.
    """
    tasks = get_tasks_by_content(sg, project_name, from_content)
    if not tasks:
        logger.info("No '%s' tasks found in project '%s'. Nothing to do.", from_content, project_name)
        return []
    if dry_run:
        logger.info("[DRY-RUN] Would rename %d '%s' tasks -> '%s' in '%s'.",
                    len(tasks), from_content, to_content, project_name)
        return tasks
    logger.debug("Renaming %d '%s' tasks -> '%s' in '%s'.",
                len(tasks), from_content, to_content, project_name)
    total_updated = 0
    for chunk in _chunked(tasks, _BATCH_CHUNK_SIZE):
        batch = [
            {"request_type": "update", "entity_type": "Task",
             "entity_id": t["id"], "data": {"content": to_content}}
            for t in chunk
        ]
        sg.batch(batch)
        total_updated += len(chunk)
        if on_chunk:
            on_chunk(total_updated, len(tasks))
        logger.debug("Batch progress: %d / %d tasks updated.", total_updated, len(tasks))
    remaining = get_tasks_by_content(sg, project_name, from_content)
    if remaining:
        raise ValueError(
            f"Verification failed: {len(remaining)} '{from_content}' tasks still remain "
            f"in '{project_name}' after rename. Manual check required."
        )
    logger.debug("Verification passed: 0 '%s' tasks remain in '%s'.", from_content, project_name)
    return tasks

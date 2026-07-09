# Sandbox Cleanup

`gishant sandbox cleanup` deletes an AYON path hierarchy (and its matching Kitsu, ShotGrid, and
NAS-storage entities) across all four backends. AYON is the source of truth: the path is resolved
against the AYON folder tree, and Kitsu/ShotGrid/storage are discovered from that folder list.

It is a destructive tool, so it is built around a **dry run by default** plus a set of pre-flight
guardrails that make the real age, authorship, and full path of the target obvious before anything
is deleted. The guardrails exist because a dry run once listed 27 ShotGrid entities that looked like
fresh sandbox data but were ~20 months of real production work by five artists.

## Invocation

```bash
gishant sandbox cleanup -p <PROJECT> '<glob-path>' --server <test|production> [flags]
```

- `<PROJECT>` must be in the allowlist (see [Project allowlist](#project-allowlist)).
- `<glob-path>` is an AYON path and may contain glob metacharacters (`*`, `?`, `[…]`) in any
  segment. Quote it so the shell does not expand it.
- Dry run is the default. Nothing is deleted until you pass `--execute`.

There is also a whole-project mode, `--projects '<name-glob>'`, which matches and deletes entire
projects across every backend. It is mutually exclusive with the path argument and does not accept
the date-window flags; the rest of this document covers **path mode**, the common case.

## Flags

| Flag                          | Default      | Description                                                                                                                |
| ----------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `PATH` (argument)             | —            | AYON path to delete; supports glob segments. Mutually exclusive with `--projects`.                                         |
| `-p`, `--project <KEY>`       | `SGAYONTEST` | Project key for path mode. Must be in the allowlist.                                                                       |
| `--projects <GLOB>`           | —            | Whole-project mode: delete every project whose name matches the glob. Mutually exclusive with `PATH`.                      |
| `--dry-run` / `--execute`     | `--dry-run`  | Preview the plan (default) or actually perform the deletions.                                                              |
| `--server <test\|production>` | `test`       | Target environment. `production` is real, irreversible data.                                                               |
| `--created-after <DATE>`      | —            | Only delete entities created on/after `DATE`. Path mode only. See [Date filter](#date-filter-option-a-leaf-level-scalpel). |
| `--created-before <DATE>`     | —            | Only delete entities created on/before `DATE`. Path mode only.                                                             |
| `--skip-kitsu`                | off          | Do not touch Kitsu.                                                                                                        |
| `--skip-shotgrid`             | off          | Do not touch ShotGrid.                                                                                                     |
| `--skip-ayon`                 | off          | Do not delete AYON folders (AYON is still resolved to drive discovery).                                                    |
| `--skip-storage`              | off          | Do not touch NAS storage.                                                                                                  |

`DATE` accepts a bare `YYYY-MM-DD` date or a full ISO 8601 datetime, and is always interpreted in
**UTC**. A bare `--created-before` date covers the whole day (up to `23:59:59.999999Z`).

## Dry run vs execute

Dry run is the default and is safe to run at any time — it connects read-only, prints the full plan,
and ends with:

```
DRY RUN -- nothing was deleted. Pass --execute to delete.
```

Passing `--execute` prints the same plan and then asks for interactive confirmation:

```
This will PERMANENTLY delete all items above from '<PROJECT>'. Continue?
```

Answering no aborts. On `--server production` the deletions hit live production data and **cannot be
undone** — read the plan carefully first.

## Reading the plan

Every run prints the plan to the terminal (via the Rich console on stderr); machine-readable stdout
is left clean. The plan is made of the following pieces.

### Cleanup target banner

A yellow panel at the top echoes back exactly what was resolved: the project, the server
(`test`/`production`), the raw glob you passed, and each **resolved AYON path with its folder type**
(e.g. `/episodes/hitro104/hitro106_0010 (Sequence)`), plus a count of descendant folders swept in
under the match. When a date filter is active it also shows the window.

### RISK banner

Computed from the ShotGrid entities/tasks/versions in the plan. If the target does **not** look like
fresh sandbox data — heuristic: any entity predates today, or more than one distinct author is
present — a bold red panel is shown, for example:

```
26/27 entities predate today (oldest 2024-11-21; 5 author(s): ...).
This is not fresh sandbox data -- confirm before --execute.
```

If the target does look fresh, a quiet one-line confirmation is shown instead
(`Target looks sandbox-fresh: N entity(ies), all created today, M author(s).`). When a date filter
is active, the banner reflects the **post-filter** set.

### Entity tables

The AYON, Kitsu, and ShotGrid tables list what will be deleted. Beyond the type/name/ID, they carry:

- **Created** and **By** columns — the entity's `created_at` date and author, so age and ownership
  are visible at a glance. ShotGrid always populates these; Kitsu populates them when the backend
  exposes them cheaply.
- **Path** — the full AYON path of each entity. ShotGrid Tasks and Versions resolve to their parent
  shot's full path.
- **Source** — how the row entered the plan: `matched` (it directly matched the path glob),
  `descendant` (a child folder swept in under a match), or `attached` (a task/version hanging off a
  matched or descendant entity).

### Path-anchored ShotGrid matching

ShotGrid entities are first matched by `code` project-wide, which on its own could grab a same-named
sequence or shot that lives under a **different episode**. To close that hole, each matched entity
is then verified against the target path's episode (the segment after `/episodes/`):

- An entity whose own episode link (`sg_episode` for a sequence; `sg_scene`, or its sequence's
  `sg_episode`, for a shot) resolves to a **different** episode is **dropped** from the plan and
  reported: `Dropped N ShotGrid entity(ies) -- episode mismatch, not in delete plan:`.
- An entity whose episode link is **unpopulated** (cannot be resolved) is **kept** — AYON already
  resolved it under the target path — but reported as `episode-unverified` so nothing is silently
  kept or dropped.
- For non-episode targets (e.g. `/assets/...`) the check is skipped.

### Preserved by date filter table

Only shown when a date filter is active. A dim yellow panel lists every entity that was **excluded
from deletion** (preserved) because it fell outside the window or had no datestamp, with its
backend, type, name, created date, and the reason (`out of window` / `no date`). A summary line
reports `Date filter: N entity(ies) kept, M excluded (preserved)`.

## Date filter (Option A: leaf-level scalpel)

`--created-after` / `--created-before` restrict the plan to entities whose timestamp falls inside
the inclusive UTC window. The guiding rule is **never delete an out-of-window entity, and never
widen a delete to reach an in-window one** — the filter only ever prunes, never expands, the plan.

- **ShotGrid and Kitsu** leaf entities are filtered individually by their own `created_at`.
  Out-of-window and undateable entities are preserved and listed in the preserved table (the tool
  never deletes what it cannot date).
- **AYON** deletion is folder-cascade-only: deleting a folder with `force=True` removes its whole
  subtree server-side. So a folder is deleted **only when its entire subtree is in-window**. An
  out-of-window folder is always preserved; a fully in-window subtree under an old parent is deleted
  on its own. In-window leaf entities that live inside a preserved folder are still pruned on
  ShotGrid/Kitsu/NAS, but AYON has no version-level delete, so those entities remain as AYON
  products/versions inside the kept folder. The run prints a note whenever this happens.
- **NAS storage** is pruned at the **file level by filesystem mtime**: only files whose mtime is in
  the window are deleted, and a parent directory is never removed under a filter.

> **NAS mtime caveat.** NAS files are filtered by their filesystem **mtime**, which is independent
> of the ShotGrid `created_at` used for the tracked entities. A file that was copied, re-rendered,
> or otherwise touched after publish will have a newer mtime than its ShotGrid version's creation
> date, so a date window can select NAS media that does **not** line up one-to-one with the ShotGrid
> entities it keeps or preserves. In particular a narrow `--created-after` window can over-delete
> media relative to ShotGrid. Review the NAS Storage table in the dry run before using `--execute`.

## Project allowlist

Path mode only runs against a project key that is in the allowlist defined in
`src/gishant_scripts/sandbox/projects.toml`. Currently allowed: **`SGAYONTEST`** and **`WEDRO`**.
Any other key is refused before anything is contacted:

```
REFUSED: Project '<KEY>' is not in the config allowlist.
Allowed projects: SGAYONTEST, WEDRO
```

## Examples

All examples use the `SGAYONTEST` sandbox project.

### 1. Plain dry run

Preview everything that a path would delete, without touching anything:

```bash
gishant sandbox cleanup -p SGAYONTEST '/episodes/ep_test/*'
```

This resolves the path, prints the Cleanup target banner, the RISK banner, and the per-backend
tables, then ends with `DRY RUN -- nothing was deleted.` Run this first, always.

### 2. Scoped undo of a bad same-day generate

You generated sandbox data today into a sequence that also holds older real work, and want to remove
only today's entities. Scope the delete to the date window — old folders and entities are preserved:

```bash
gishant sandbox cleanup -p SGAYONTEST '/episodes/ep_test/sq010*' --created-after 2026-07-09
```

Only entities created on/after 2026-07-09 (UTC) stay in the plan; everything older, plus anything
undateable, is listed in the Preserved by date filter table. This is still a dry run — add
`--execute` once the plan looks right. (Mind the NAS mtime caveat above.)

### 3. Executing the delete

Perform the deletion after reviewing the dry run. You will be asked to confirm:

```bash
gishant sandbox cleanup -p SGAYONTEST '/episodes/ep_test' --execute
```

The same command against production is **irreversible** — there is no undo once it runs:

```bash
gishant sandbox cleanup -p SGAYONTEST '/episodes/ep_test' --server production --execute
```

Only use `--server production --execute` after reading the plan, the RISK banner, and (if filtering)
the Preserved table, and confirming the target is what you expect.

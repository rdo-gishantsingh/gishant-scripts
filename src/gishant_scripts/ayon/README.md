# AYON Bundle Management Tools

Tools for analyzing and synchronizing AYON bundle configurations.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [analyze-bundles](#analyze-bundles)
- [sync-bundles](#sync-bundles)
- [Environment Options](#environment-options)
- [Backup & Recovery](#backup--recovery)

---

## Quick Start

```bash
# Compare two bundles (show only differences)
gishant analyze-bundles dev_bundle staging_bundle --only-diff

# Preview sync changes (dry-run)
gishant sync-bundles dev_bundle staging_bundle --dry-run

# Sync specific addon only
gishant sync-bundles dev_bundle staging_bundle -a maya --dry-run
```

---

## Installation

```bash
# Install dependencies
uv pip install ayon-python-api rich click

# Configure environment (.env file)
AYON_SERVER_URL=http://ayon-server:5000
AYON_API_KEY=your-api-key

# For dev/local servers
AYON_SERVER_URL_DEV=http://ayon-dev:5000
AYON_API_KEY_DEV=your-dev-key
AYON_SERVER_URL_LOCAL=http://localhost:5000
AYON_API_KEY_LOCAL=your-local-key
```

---

## analyze-bundles

Compare settings between two AYON bundles.

### Synopsis

```bash
gishant analyze-bundles [BUNDLE1] [BUNDLE2] [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `BUNDLE1` | First bundle name (optional if interactive) |
| `BUNDLE2` | Second bundle name (optional if interactive) |
| `--only-diff` | Show only differences, hide unchanged |
| `--max-depth N` | Limit nesting depth for comparison |
| `--view MODE` | Display mode: `table`, `tree`, or `both` (default: table) |
| `-o, --output FILE` | Export to file (.json or .md) |
| `-p, --project NAME` | Include project-specific settings |
| `-a, --addon NAME` | Filter to addon(s), can repeat |
| `-i, --interactive` | Interactive bundle/project selection |
| `--local` | Use local environment |
| `--dev` | Use dev environment |

### Examples

#### Basic Comparison

```bash
# Compare two bundles
gishant analyze-bundles production_bundle staging_bundle

# Show only differences
gishant analyze-bundles production_bundle staging_bundle --only-diff

# Interactive mode - select bundles from list
gishant analyze-bundles --interactive
gishant analyze-bundles -i
```

#### View Modes

```bash
# Table view (default) - clean tabular format
gishant analyze-bundles dev staging --view table

# Tree view - hierarchical with diff symbols (+, -, ~)
gishant analyze-bundles dev staging --view tree

# Both views
gishant analyze-bundles dev staging --view both
```

#### Addon Filtering

```bash
# Filter to single addon
gishant analyze-bundles dev staging -a maya

# Filter to multiple addons
gishant analyze-bundles dev staging -a maya -a nuke -a houdini

# Filter with only-diff
gishant analyze-bundles dev staging -a maya --only-diff
```

#### Project-Specific Comparison

```bash
# Include project settings and anatomy
gishant analyze-bundles dev staging -p MyProject

# Interactive project selection
gishant analyze-bundles dev staging -i

# Project + addon filter
gishant analyze-bundles dev staging -p MyProject -a maya --only-diff
```

#### Export Results

```bash
# Export to JSON
gishant analyze-bundles dev staging -o comparison.json

# Export to Markdown
gishant analyze-bundles dev staging -o comparison.md

# Export with all options
gishant analyze-bundles dev staging \
  --only-diff \
  -a maya \
  -p MyProject \
  -o report.md
```

#### Depth Control

```bash
# Limit comparison depth (faster for large configs)
gishant analyze-bundles dev staging --max-depth 2

# Unlimited depth (default)
gishant analyze-bundles dev staging --max-depth 0
```

#### Environment Selection

```bash
# Production server (default)
gishant analyze-bundles dev staging

# Dev server
gishant analyze-bundles dev staging --dev

# Local server
gishant analyze-bundles dev staging --local
```

### Output

**Table View:**
```
╭─ dev_bundle vs staging_bundle ─╮
╰────────────────────────────────╯

                    📋 Bundle Metadata
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Setting          ┃ dev_bundle ┃ staging    ┃ Status   ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ installerVersion │ 1.4.2      │ 1.4.0      │ changed  │
└──────────────────┴────────────┴────────────┴──────────┘

Summary: 42 items compared, 5 differences
  3 changed, 1 added, 1 removed, 38 unchanged
```

**Tree View:**
```
Bundle Comparison: dev_bundle vs staging_bundle
├── 📋 Metadata
│   └── ~ installerVersion: 1.4.2 → 1.4.0
├── 🔌 Addons
│   ├── ~ maya: 1.2.0 → 1.1.0
│   └── + nuke: 2.0.0
└── ⚙️  Studio Settings
    └── maya
        └── - maya.render.defaultRenderer: arnold
```

---

## sync-bundles

Synchronize settings between AYON bundles and projects.

### Synopsis

```bash
gishant sync-bundles [SOURCE] [TARGET] [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `SOURCE` | Source bundle/project name (required unless `-i`) |
| `TARGET` | Target bundle/project name (required unless `-i`) |
| `-op, --operation` | Operation: `bundle`, `project-bundle`, `project` (default: bundle) |
| `-p, --project NAME` | Project name (required for `project-bundle` operation) |
| `-b, --bundle NAME` | Bundle context (required for `project` operation) |
| `--sync-mode MODE` | Mode: `diff-only` or `all` (default: diff-only) |
| `-a, --addon NAME` | Filter to addon(s), can repeat |
| `--dry-run` | Preview changes without applying |
| `-f, --force` | Skip confirmation prompts |
| `-i, --interactive` | Interactive guided mode |
| `--local` | Use local environment |
| `--dev` | Use dev environment |

### Operations

| Operation | Description | Required Options |
|-----------|-------------|------------------|
| `bundle` | Sync source bundle → target bundle | None |
| `project-bundle` | Lift project settings → bundle studio defaults | `--project` |
| `project` | Clone project → project settings | `--bundle` |

### Examples

#### Bundle to Bundle Sync

```bash
# Preview changes (always do this first!)
gishant sync-bundles dev_bundle staging_bundle --dry-run

# Apply sync
gishant sync-bundles dev_bundle staging_bundle

# Force sync without confirmation
gishant sync-bundles dev_bundle staging_bundle --force

# Sync all settings (not just differences)
gishant sync-bundles dev_bundle staging_bundle --sync-mode all
```

#### Addon-Specific Sync

```bash
# Sync only maya addon
gishant sync-bundles dev staging -a maya --dry-run

# Sync multiple addons
gishant sync-bundles dev staging -a maya -a nuke --dry-run

# Sync multiple addons and apply
gishant sync-bundles dev staging -a maya -a nuke -a houdini
```

#### Project to Bundle Sync

Promote project-specific overrides to studio defaults:

**Note:** For `project-bundle` operation, SOURCE and TARGET are both bundle names. The `--project` option specifies which project's settings to lift to studio defaults.

```bash
# Preview project → bundle sync
# SOURCE = bundle containing the project settings
# TARGET = bundle where studio settings will be updated
# --project = project name whose settings will be promoted
gishant sync-bundles source_bundle target_bundle \
  --operation project-bundle \
  --project MyProject \
  --dry-run

# Apply project overrides to studio defaults
gishant sync-bundles source_bundle target_bundle \
  --operation project-bundle \
  --project MyProject

# With addon filter
gishant sync-bundles source_bundle target_bundle \
  --operation project-bundle \
  --project MyProject \
  -a maya --dry-run
```

#### Project to Project Sync

Clone settings between projects:

```bash
# Preview project clone
gishant sync-bundles TemplateProject NewProject \
  --operation project \
  --bundle production_bundle \
  --dry-run

# Clone project settings
gishant sync-bundles TemplateProject NewProject \
  --operation project \
  --bundle production_bundle

# Clone only specific addons
gishant sync-bundles TemplateProject NewProject \
  --operation project \
  --bundle production_bundle \
  -a maya -a nuke
```

#### Interactive Mode

```bash
# Fully guided sync wizard
gishant sync-bundles --interactive
gishant sync-bundles -i

# Interactive with dev server
gishant sync-bundles -i --dev
```

#### Environment Selection

```bash
# Production server (default)
gishant sync-bundles dev staging --dry-run

# Dev server
gishant sync-bundles dev staging --dev --dry-run

# Local server
gishant sync-bundles dev staging --local --dry-run
```

#### CI/CD Automation

```bash
# Non-interactive, no prompts
gishant sync-bundles dev staging --force --dry-run

# Apply with logging
gishant sync-bundles dev staging --force 2>&1 | tee sync.log

# Addon-specific automated sync
gishant sync-bundles dev staging -a maya --force
```

### Output

```
AYON Bundle Sync

Connecting to AYON (dev)...
✓ Connected to AYON server (dev): http://ayondev.redefine.co/
✓ Found 168 bundles

╭──────────────────────────────────────────────────────────────────────────────╮
│ dev_bundle → staging_bundle | Filter: maya | DRY RUN                         │
╰──────────────────────────────────────────────────────────────────────────────╯

                                   📦 ADDONS
┏━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Setting ┃ dev_bundle    ┃ staging_bundle  ┃ Status   ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ maya    │ 1.2.0         │ 1.1.0           │ changed  │
└─────────┴───────────────┴─────────────────┴──────────┘

DRY RUN: 15 change(s) would be applied
```

---

## Environment Options

Both tools support multiple AYON server environments:

| Flag | Environment Variables |
|------|----------------------|
| (default) | `AYON_SERVER_URL`, `AYON_API_KEY` |
| `--dev` | `AYON_SERVER_URL_DEV`, `AYON_API_KEY_DEV` |
| `--local` | `AYON_SERVER_URL_LOCAL`, `AYON_API_KEY_LOCAL` |

```bash
# Production
gishant analyze-bundles dev staging

# Development server
gishant analyze-bundles dev staging --dev

# Local development
gishant analyze-bundles dev staging --local
```

---

## Backup & Recovery

### Automatic Backups

`sync-bundles` creates automatic backups before any changes:

```
~/.ayon/sync_backups/
  ├── bundle_staging_bundle_20241202_143022.json
  ├── bundle_production_MyProject_bundle_from_project_20241202_150000.json
  └── production_NewProject_project_20241202_160000.json
```

### Restore from Backup

```python
from gishant_scripts.ayon.sync_bundles import restore_from_backup
from pathlib import Path
from rich.console import Console

console = Console()
backup_file = Path("~/.ayon/sync_backups/bundle_staging_20241202_143022.json").expanduser()
settings = restore_from_backup(backup_file, console)
```

---

## Common Workflows

### 1. Dev → Staging → Production Pipeline

```bash
# Step 1: Preview dev → staging
gishant analyze-bundles dev staging --only-diff
gishant sync-bundles dev staging --dry-run

# Step 2: Apply to staging
gishant sync-bundles dev staging

# Step 3: Preview staging → production
gishant analyze-bundles staging production --only-diff
gishant sync-bundles staging production --dry-run

# Step 4: Deploy to production
gishant sync-bundles staging production
```

### 2. Update Single Addon Across Environments

```bash
# Check maya differences
gishant analyze-bundles dev production -a maya --only-diff

# Preview maya sync
gishant sync-bundles dev production -a maya --dry-run

# Apply maya only
gishant sync-bundles dev production -a maya
```

### 3. Clone Project Template

```bash
# Preview clone
gishant sync-bundles Template NewShow \
  --operation project \
  --bundle production \
  --dry-run

# Apply clone
gishant sync-bundles Template NewShow \
  --operation project \
  --bundle production
```

### 4. Promote Project Settings to Studio Defaults

```bash
# Find project overrides
gishant analyze-bundles production -p SuccessfulShow --only-diff

# Preview promotion (project settings → studio defaults)
gishant sync-bundles production_bundle new_production_bundle \
  --operation project-bundle \
  --project SuccessfulShow \
  --dry-run

# Apply promotion
gishant sync-bundles production_bundle new_production_bundle \
  --operation project-bundle \
  --project SuccessfulShow
```

---

## Status Legend

| Status | Color | Meaning |
|--------|-------|---------|
| `unchanged` | dim | Values match |
| `changed` | yellow | Values differ |
| `added` | cyan | Only in second bundle |
| `removed` | red | Only in first bundle |

**Tree View Symbols:**

- `+` Added (cyan)
- `-` Removed (red)
- `~` Changed (yellow)

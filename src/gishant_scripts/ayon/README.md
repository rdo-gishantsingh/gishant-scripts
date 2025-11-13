# AYON Bundle Management Tools - Complete Manual

Comprehensive documentation for AYON bundle analysis and synchronization tools.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Tool Reference](#tool-reference)
  - [analyze-bundles](#analyze-bundles)
  - [sync-bundles](#sync-bundles)
- [Core Concepts](#core-concepts)
- [Common Workflows](#common-workflows)
- [Safety Features](#safety-features)
- [Best Practices](#best-practices)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [API Reference](#api-reference)


## Overview

These professional-grade tools provide comprehensive bundle management for AYON production pipelines, enabling teams to analyze, compare, and synchronize settings across environments with enterprise-level safety features.

### What Can You Do?

**Bundle Analysis (`analyze-bundles`)**
- 🔍 **Compare Bundles**: Identify all differences between any two AYON bundles
- 📊 **Multiple Views**: Table view for quick scanning, tree view for hierarchical exploration
- 🎯 **Focused Analysis**: Filter by specific addons, categories, or projects
- 💾 **Export Results**: Save comparisons to JSON or Markdown for documentation
- 🔬 **Deep Inspection**: Compare addon versions, studio settings, project overrides, anatomy, and dependencies

**Bundle Synchronization (`sync-bundles`)**
- 🔄 **Bundle-to-Bundle Sync**: Promote settings from dev → staging → production
- 🎯 **Project-to-Bundle Sync**: Lift project-specific settings to studio defaults
- 🔀 **Project-to-Project Sync**: Clone configurations between projects
- 🎛️ **Selective Sync**: Sync specific addons only for surgical updates
- 🛡️ **Safety First**: Automatic backups, dry-run preview, rollback capability
- ⚡ **Batch Operations**: Sync multiple addons in one operation

### Key Features

| Feature | Description |
|---------|-------------|
| **Interactive Mode** | Guided workflows with menu-driven selection |
| **Dry-Run Preview** | See exactly what will change before applying |
| **Automatic Backups** | Every sync creates timestamped backups |
| **Diff-Only Mode** | Sync only what's different (recommended) |
| **Addon Filtering** | Focus on specific addons like Maya, Nuke, or custom |
| **Rich Terminal UI** | Beautiful tables, trees, and progress indicators |
| **Rollback Support** | Restore from backups if something goes wrong |
| **Audit Trail** | Comprehensive logging of all operations |

### Use Cases

**Pipeline Engineers:**
- Compare bundle configurations before deployment
- Sync settings across development environments
- Audit differences between production and staging

**TDs & Artists:**
- Identify why settings differ between projects
- Clone project configurations for new shows
- Verify addon versions match expectations

**Production Management:**
- Maintain consistency across projects
- Roll out studio-wide settings updates
- Track configuration changes over time

## Quick Start

### 1. Compare Two Bundles

```bash
# Interactive mode - select bundles from menu
gishant analyze-bundles --interactive

# Or specify bundles directly
gishant analyze-bundles production-v1.0.0 staging-v1.1.0
```

### 2. Sync Settings Between Bundles

```bash
# Preview what would change (dry-run)
gishant sync-bundles production staging --dry-run

# Apply the sync
gishant sync-bundles production staging
```

### 3. Sync Specific Addon Only

```bash
# Sync only Maya addon settings
gishant sync-bundles dev-bundle prod-bundle --addon maya
```

### 4. Export Comparison Report

```bash
# Generate Markdown report
gishant analyze-bundles prod staging --output report.md

# Generate JSON for further processing
gishant analyze-bundles prod staging --output data.json
```


## Installation

### Prerequisites

- **Python 3.11+** required
- **AYON Server** accessible via network
- **AYON API credentials** (API key with appropriate permissions)

### Install from Source

```bash
# Clone repository
cd /path/to/gishant-scripts

# Install with poetry (recommended)
poetry install

# Or install with pip
pip install -e .

# Verify installation
gishant --help
```

### Dependencies

The following packages are automatically installed:

| Package | Purpose | Version |
|---------|---------|---------|
| `ayon-python-api` | AYON server API client | Latest |
| `rdo-ayon-utils` | Connection and auth helpers | Latest |
| `rich` | Terminal UI and formatting | ≥13.0 |
| `click` | CLI framework | ≥8.0 |

### Configuration

#### 1. Set AYON Server URL

```bash
# Set environment variable
export AYON_SERVER_URL="http://ayon-server:5000"

# Or create config file at ~/.ayon/config.json
{
  "server_url": "http://ayon-server:5000"
}
```

#### 2. Configure Authentication

The tools use `rdo-ayon-utils` for authentication, which supports multiple methods:

**Method 1: Environment Variable**
```bash
export AYON_API_KEY="your-api-key-here"
```

**Method 2: Configuration File**
```json
// ~/.ayon/config.json
{
  "server_url": "http://ayon-server:5000",
  "api_key": "your-api-key-here"
}
```

**Method 3: Interactive Login**
The tools will prompt for credentials if not configured.

#### 3. Verify Connection

```bash
# Test AYON connection
python -c "import ayon_api; print(ayon_api.get_server_api_connection())"

# Or use rdo-ayon-utils
python -c "from rdo_ayon_utils import ayon_utils; ayon_utils.connect()"
```

### Permissions Required

Your AYON API key needs these permissions:

| Operation | Required Permission |
|-----------|-------------------|
| Analyze bundles | `bundles.read` |
| Sync bundles | `bundles.read`, `bundles.write` |
| Project operations | `projects.read`, `projects.write` |
| Anatomy modifications | `anatomy.write` |

## Core Concepts

### AYON Bundles

An AYON bundle is a versioned configuration package containing:

1. **Metadata**: Name, version, creation date, is_dev/is_production flags
2. **Addon Versions**: Specific versions of addons (Maya, Nuke, etc.)
3. **Studio Settings**: Global studio-wide configurations
4. **Dependency Packages**: Platform-specific package dependencies

**Bundle Types:**
- **Development Bundles** (`isDev=true`): Editable, for testing
- **Staging Bundles** (`isStaging=true`): Pre-production testing
- **Production Bundles** (`isProduction=true`): Locked, deployed to artists

### Settings Hierarchy

AYON uses a three-tier settings hierarchy:

```
Studio Settings (Bundle)
    ↓
Project Settings (Project-specific overrides)
    ↓
Anatomy (Project folder structure)
```

**Understanding Overrides:**
- **Studio Settings**: Default values for all projects
- **Project Settings**: Override studio defaults for specific project
- **Anatomy**: Defines folder templates and naming conventions

### Addon Filtering

Both tools support filtering by addon name:

```bash
# Analyze only Maya addon
gishant analyze-bundles prod dev --addon maya

# Sync only Nuke addon
gishant sync-bundles prod dev --addon nuke
```

**Common Addons:**
- `maya` - Autodesk Maya integration
- `nuke` - Foundry Nuke integration
- `unreal` - Unreal Engine integration
- `houdini` - SideFX Houdini integration
- `deadline` - Render farm integration
- `kitsu` - Production tracking integration

### Comparison Modes

**Diff-Only Mode** (default):
- Only shows/syncs settings that differ
- Recommended for most operations
- Faster and safer

**All Mode**:
- Shows/syncs all settings regardless of differences
- Useful for complete configuration cloning
- Use with caution in production

### Dry-Run vs. Live Sync

**Dry-Run Mode** (`--dry-run`):
- Previews changes without applying
- No modifications to AYON server
- Safe for testing and validation
- Always recommended first

**Live Sync**:
- Actually applies changes to AYON
- Creates automatic backups
- Requires confirmation (unless `--force`)
- Irreversible without rollback

## Tool Reference

### analyze-bundles

Comprehensive analysis and comparison of AYON bundles.

#### Synopsis

```bash
gishant analyze-bundles [BUNDLE1] [BUNDLE2] [OPTIONS]
```


#### Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `BUNDLE1` | First bundle name | No* |
| `BUNDLE2` | Second bundle name | No* |

\* If not provided, interactive mode is triggered

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--only-diff` | Flag | False | Show only differences (hide matching values) |
| `--max-depth <n>` | Integer | Unlimited | Maximum nesting depth for comparison |
| `--view <mode>` | Choice | both | Display mode: `table`, `tree`, or `both` |
| `--output <path>` | Path | None | Export to file (.json or .md extension) |
| `--project <name>` | String | None | Include project-specific comparison |
| `--interactive` / `-i` | Flag | False | Interactive mode with menu selection |

#### View Modes

**Table View** - Best for quick scanning:
```
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Setting       ┃ Bundle 1        ┃ Bundle 2        ┃ Status   ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ fps           │ 24              │ 25              │ Changed  │
│ resolution    │ 1920x1080       │ 3840x2160       │ Changed  │
│ maya.version  │ 1.0.0           │ 1.1.0           │ Changed  │
└───────────────┴─────────────────┴─────────────────┴──────────┘
```

**Tree View** - Best for hierarchical exploration:
```
Bundle Comparison: production-v1.0.0 vs staging-v1.1.0
├── 📋 Metadata
│   ├── name: production-v1.0.0 → staging-v1.1.0
│   └── version: 1.0.0 → 1.1.0
├── 🔌 Addon Versions
│   ├── maya: 1.0.0 → 1.1.0 (changed)
│   └── nuke: 2.0.1 → 2.0.1 (unchanged)
├── ⚙️  Studio Settings
│   ├── general
│   │   ├── fps: 24 → 25
│   │   └── resolution: 1920x1080 → 3840x2160
│   └── maya
│       └── defaultRenderer: arnold → renderman
└── 🏗️  Project Anatomy
    └── templates
        └── work: templates/work/v001 → templates/work/v002
```

#### Examples

**Basic Comparison:**
```bash
# Compare two bundles interactively
gishant analyze-bundles --interactive

# Compare specific bundles
gishant analyze-bundles production-v1.0.0 staging-v1.1.0

# Show only differences
gishant analyze-bundles prod staging --only-diff
```

**View Mode Selection:**
```bash
# Table view only
gishant analyze-bundles prod staging --view table

# Tree view only (hierarchical)
gishant analyze-bundles prod staging --view tree

# Both views (default)
gishant analyze-bundles prod staging --view both
```

**Project-Specific Analysis:**
```bash
# Include project-specific settings
gishant analyze-bundles prod staging --project Bollywoof

# Interactive project selection
gishant analyze-bundles prod staging --project
```

**Export Results:**
```bash
# Export to JSON
gishant analyze-bundles prod staging --output comparison.json

# Export to Markdown
gishant analyze-bundles prod staging --output report.md

# Export with project data
gishant analyze-bundles prod staging --project Bollywoof --output full-report.md
```

**Control Comparison Depth:**
```bash
# Limit to top 2 levels (faster for large configs)
gishant analyze-bundles prod staging --max-depth 2

# Unlimited depth (default)
gishant analyze-bundles prod staging
```

#### Output Files

**JSON Format** (`.json` extension):
```json
{
  "comparison": {
    "metadata": {
      "bundle1": {...},
      "bundle2": {...}
    },
    "addons": {...},
    "settings": {...},
    "project_settings": {...},
    "anatomy": {...}
  },
  "differences": {
    "metadata": [...],
    "addons": [...],
    "settings": [...]
  },
  "timestamp": "2024-01-15T14:30:22"
}
```

**Markdown Format** (`.md` extension):
```markdown
# Bundle Comparison: production-v1.0.0 vs staging-v1.1.0

Generated: 2024-01-15 14:30:22

## 📋 Bundle Metadata

| Setting | production-v1.0.0 | staging-v1.1.0 | Status |
|---------|------------------|----------------|--------|
| name    | production-v1.0.0 | staging-v1.1.0 | Changed |

## 🔌 Addon Versions

| Addon | production-v1.0.0 | staging-v1.1.0 | Status |
|-------|------------------|----------------|--------|
| maya  | 1.0.0            | 1.1.0          | Changed |
...
```

#### Interactive Mode

When launched with `--interactive` or without bundle arguments:

**Step 1: Bundle Selection**
```
Available bundles:
  1. production-v1.0.0 (production)
  2. staging-v1.1.0 (staging)
  3. dev-latest (development)

Select first bundle [1-3]: 1
Select second bundle [1-3]: 2
```

**Step 2: Project Selection (Optional)**
```
Include project-specific comparison? [y/N]: y

Available projects:
  1. Bollywoof
  2. ProjectX
  3. Demo

Select project [1-3]: 1
```

**Step 3: Display Options**
```
View mode:
  1. Table (best for quick scanning)
  2. Tree (best for hierarchy)
  3. Both (default)

Choice [1-3]: 3

Show only differences? [Y/n]: y
```

**Step 4: Export Options**
```
Export results to file? [y/N]: y
Output format:
  1. JSON
  2. Markdown

Choice [1-2]: 2
Output file: bundle-comparison.md
```

---

### sync-bundles

Synchronize settings and configurations between AYON bundles and projects with enterprise-level safety features.

#### Synopsis

```bash
gishant sync-bundles [SOURCE] [TARGET] [OPTIONS]
```

#### Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `SOURCE` | Source bundle/project name | No* |
| `TARGET` | Target bundle/project name | No* |

\* Required unless using `--interactive` mode


#### Options

**Sync Operation Type:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--operation` / `-op` | Choice | `bundle` | Operation type: `bundle`, `project-bundle`, `project` |

**Target Configuration:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--project` / `-p` | String | None | Project name (required for project operations) |
| `--bundle` / `-b` | String | None | Bundle context for project operations |

**Sync Settings:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--sync-mode` | Choice | `diff-only` | Sync mode: `diff-only` or `all` |
| `--addon` / `-a` | String | None | Sync only specific addon (can use multiple times) |

**Execution Control:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | False | Preview changes without applying |
| `--force` / `-f` | Flag | False | Skip confirmation prompts |
| `--interactive` / `-i` | Flag | False | Guided interactive mode |

#### Operation Types

**1. Bundle-to-Bundle (`--operation bundle`)**

Sync settings from one bundle to another.

**Use Cases:**
- Promote dev settings to staging
- Deploy staging settings to production
- Clone bundle configurations

**Example:**
```bash
gishant sync-bundles dev-bundle prod-bundle --operation bundle
```

**What Gets Synced:**
- ✅ Addon versions
- ✅ Studio settings
- ✅ Dependency packages
- ❌ Project-specific settings (not applicable)
- ❌ Project anatomy (not applicable)

---

**2. Project-to-Bundle (`--operation project-bundle`)**

Lift project-specific settings to studio defaults in a bundle.

**Use Cases:**
- Promote project overrides to studio defaults
- Standardize settings across all projects
- Update bundle based on successful project configuration

**Example:**
```bash
gishant sync-bundles \
  --operation project-bundle \
  --project Bollywoof \
  --bundle source-bundle \
  target-bundle
```

**What Gets Synced:**
- ✅ Project settings → Studio settings
- ✅ Project-specific addon configurations
- ❌ Anatomy (stays project-specific)
- ❌ Addon versions (handled separately)

---

**3. Project-to-Project (`--operation project`)**

Clone settings from one project to another.

**Use Cases:**
- Create new project from template
- Replicate successful project configuration
- Standardize settings across shows

**Example:**
```bash
gishant sync-bundles \
  --operation project \
  template-project new-project \
  --bundle production \
  --project new-project
```

**What Gets Synced:**
- ✅ Project settings
- ✅ Project anatomy
- ✅ Project-specific addon overrides
- ❌ Studio settings (not project-specific)

#### Sync Modes

**Diff-Only Mode** (`--sync-mode diff-only`) - **RECOMMENDED**

Only syncs settings that differ between source and target.

**Advantages:**
- ✅ Faster execution
- ✅ Safer (doesn't touch unchanged values)
- ✅ Clearer preview of changes
- ✅ Maintains existing configurations

**Example:**
```bash
gishant sync-bundles dev prod --sync-mode diff-only
```

---

**All Mode** (`--sync-mode all`)

Syncs all settings regardless of whether they differ.

**Use Cases:**
- Complete configuration cloning
- Ensuring absolute consistency
- Resetting to known state

**Caution:**
- ⚠️ Overwrites all target settings
- ⚠️ May reset customizations
- ⚠️ Use only when intended

**Example:**
```bash
gishant sync-bundles template-project new-project \
  --operation project \
  --sync-mode all
```

#### Examples

**Basic Bundle Sync:**

```bash
# Dry-run first (always recommended)
gishant sync-bundles dev-bundle staging-bundle --dry-run

# Apply sync
gishant sync-bundles dev-bundle staging-bundle

# Sync only differences (default)
gishant sync-bundles dev staging --sync-mode diff-only

# Force complete overwrite
gishant sync-bundles dev staging --sync-mode all --force
```

**Addon-Specific Sync:**

```bash
# Sync only Maya addon
gishant sync-bundles dev prod --addon maya

# Sync only Nuke addon
gishant sync-bundles dev prod --addon nuke

# Sync multiple specific addons
gishant sync-bundles dev prod --addon maya --addon nuke --addon houdini
```

**Project Operations:**

```bash
# Sync project settings to bundle studio defaults
gishant sync-bundles \
  --operation project-bundle \
  --project Bollywoof \
  --bundle dev-bundle \
  staging-bundle

# Clone project configuration
gishant sync-bundles \
  --operation project \
  template-project new-show \
  --bundle production \
  --project new-show

# Clone project with only Maya settings
gishant sync-bundles \
  --operation project \
  template new-project \
  --bundle prod \
  --project new-project \
  --addon maya
```

**Interactive Mode:**

```bash
# Launch guided wizard
gishant sync-bundles --interactive

# Interactive with pre-selected operation
gishant sync-bundles --interactive --operation bundle
```

**Automated/CI-CD Usage:**

```bash
# No prompts, no dry-run (use with caution)
gishant sync-bundles dev prod \
  --sync-mode diff-only \
  --addon maya \
  --force

# Log output for audit
gishant sync-bundles dev prod \
  --force 2>&1 | tee sync-$(date +%Y%m%d).log
```

#### Sync Preview

Before any sync operation (unless `--force` is used), you'll see a detailed preview:

```
╭─ Sync Operation ────────────────────────────────────────╮
│ Sync Preview: dev-bundle → production-bundle            │
│ Mode: diff-only                                          │
│ Addon Filter: maya                                       │
╰──────────────────────────────────────────────────────────╯

Changes to Apply:

📋 Metadata (0 changes)

🔌 Addon Versions (1 change)
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Addon    ┃ Current       ┃ New           ┃ Status  ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ maya     │ 1.0.0         │ 1.1.0         │ Changed │
└──────────┴───────────────┴───────────────┴─────────┘

⚙️  Studio Settings (3 changes)
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Setting               ┃ Current     ┃ New         ┃ Status  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━┩
│ maya.defaultRenderer  │ arnold      │ renderman   │ Changed │
│ maya.defaultUnits     │ cm          │ m           │ Changed │
│ maya.autoSave         │ True        │ False       │ Changed │
└───────────────────────┴─────────────┴─────────────┴─────────┘

📦 Dependencies (0 changes)

Total Changes: 4
Backup will be created: ~/.ayon/sync_backups/bundle_production_20240115_143022

⚠️  Warning: This will modify 'production-bundle' settings.

Proceed with sync? [y/N]:
```

#### Interactive Mode Flow

**Step 1: Operation Selection**
```
╭─ Sync Operation Selection ──────────────────────────────╮
│ Select the type of sync operation:                      │
│                                                          │
│   1. Bundle → Bundle    (sync between bundles)          │
│   2. Project → Bundle   (lift project to studio)        │
│   3. Project → Project  (clone project config)          │
│                                                          │
╰──────────────────────────────────────────────────────────╯

Choice [1-3]: 1
```

**Step 2: Source Selection**
```
Available bundles:
  • production-v1.0.0 (production)
  • staging-v1.1.0 (staging)
  • dev-latest (development)

Select source bundle: dev-latest
```

**Step 3: Target Selection**
```
Available bundles (excluding source):
  • production-v1.0.0 (production)
  • staging-v1.1.0 (staging)

Select target bundle: staging-v1.1.0
```

**Step 4: Sync Configuration**
```
Sync mode:
  1. Differences only (recommended)
  2. All settings

Choice [1-2]: 1

Filter to specific addon(s)? [y/N]: y
Enter addon names (comma-separated): maya, nuke
```

**Step 5: Safety Confirmation**
```
Preview changes first (dry-run)? [Y/n]: y

[Preview table displayed]

Apply these changes? [y/N]: y
```

**Step 6: Execution**
```
Creating backup...
✓ Backup created: ~/.ayon/sync_backups/bundle_staging_20240115_143022

Syncing addon versions...
✓ Updated addon: maya (1.0.0 → 1.1.0)
✓ Updated addon: nuke (2.0.1 → 2.1.0)

Syncing studio settings...
✓ Updated 3 settings

╭─ Sync Complete ──────────────────────────────────────────╮
│ Successfully synced dev-latest → staging-v1.1.0          │
│                                                           │
│ Changes Applied:                                          │
│   • Addon versions: 2 updates                            │
│   • Studio settings: 3 changes                           │
│                                                           │
│ Backup location:                                          │
│   ~/.ayon/sync_backups/bundle_staging_20240115_143022   │
╰───────────────────────────────────────────────────────────╯
```

## Common Workflows

### Workflow 1: Development → Staging → Production Pipeline

**Scenario:** Promote changes through environments safely.

**Steps:**

1. **Develop and Test in Dev Bundle**
   ```bash
   # View current dev bundle configuration
   gishant analyze-bundles dev-bundle --view table

   # Test changes in development
   # [Manual testing phase]
   ```

2. **Preview Dev → Staging Sync**
   ```bash
   # Always dry-run first
   gishant sync-bundles dev-bundle staging-bundle \
     --sync-mode diff-only \
     --dry-run
   ```

3. **Apply to Staging**
   ```bash
   # Apply changes to staging
   gishant sync-bundles dev-bundle staging-bundle \
     --sync-mode diff-only

   # Verify staging bundle
   gishant analyze-bundles staging-bundle --view table
   ```

4. **User Acceptance Testing**
   ```bash
   # [Manual UAT phase on staging]
   # Get project-specific view if needed
   gishant analyze-bundles staging-bundle \
     --project test-project \
     --view tree
   ```

5. **Promote to Production**
   ```bash
   # Final dry-run
   gishant sync-bundles staging-bundle production-bundle \
     --sync-mode diff-only \
     --dry-run

   # Production deployment
   gishant sync-bundles staging-bundle production-bundle \
     --sync-mode diff-only

   # Verification
   gishant analyze-bundles production-bundle --view table
   ```

**Best Practice Tips:**
- ✅ Always use `--dry-run` before actual sync
- ✅ Backup production bundles before sync
- ✅ Test in development thoroughly
- ✅ Document changes in each stage
- ✅ Use `--sync-mode diff-only` to avoid unnecessary overwrites

---

### Workflow 2: Project Template Management

**Scenario:** Create standardized project configurations.

**Steps:**

1. **Create Master Template Project**
   ```bash
   # Setup template project with ideal settings
   # [Configure template-project manually in AYON UI]

   # Verify template configuration
   gishant analyze-bundles production-bundle \
     --project template-project \
     --view tree
   ```

2. **Export Template Documentation**
   ```bash
   # Document template for reference
   gishant analyze-bundles production-bundle \
     --project template-project \
     --output template-config \
     --view table

   # This creates:
   # - template-config.json (machine-readable)
   # - template-config.md (human-readable)
   ```

3. **Clone Template to New Project**
   ```bash
   # Preview the clone operation
   gishant sync-bundles \
     --operation project \
     template-project new-show \
     --bundle production-bundle \
     --project new-show \
     --dry-run

   # Apply template to new project
   gishant sync-bundles \
     --operation project \
     template-project new-show \
     --bundle production-bundle \
     --project new-show
   ```

4. **Verify New Project**
   ```bash
   # Compare new project to template
   gishant analyze-bundles production-bundle \
     template-project new-show \
     --project new-show \
     --only-diff
   ```

**Advanced: Partial Template Application**

Apply only specific addons from template:

```bash
# Clone only Maya and Nuke settings
gishant sync-bundles \
  --operation project \
  template-project new-show \
  --bundle production \
  --project new-show \
  --addon maya \
  --addon nuke
```

---

### Workflow 3: Addon Version Management

**Scenario:** Update addon versions across bundles.

**Steps:**

1. **Check Current Addon Versions**
   ```bash
   # View all addon versions
   gishant analyze-bundles production-bundle staging-bundle
   ```

2. **Compare Specific Addon**
   ```bash
   # Focus on Maya addon only
   gishant analyze-bundles prod-bundle staging-bundle \
     --addon maya \
     --only-diff
   ```

3. **Preview Addon Sync**
   ```bash
   # Dry-run sync for Maya only
   gishant sync-bundles dev-bundle prod-bundle \
     --addon maya \
     --dry-run
   ```

4. **Apply Addon Update**
   ```bash
   # Update Maya addon version in production
   gishant sync-bundles dev-bundle prod-bundle \
     --addon maya
   ```

**Bulk Addon Updates:**

```bash
# Update multiple addons at once
gishant sync-bundles dev-bundle prod-bundle \
  --addon maya \
  --addon nuke \
  --addon houdini \
  --addon deadline
```

---

### Workflow 4: Project Settings Promotion

**Scenario:** Promote successful project overrides to studio defaults.

**Steps:**

1. **Identify Successful Project Overrides**
   ```bash
   # Compare project to studio defaults
   gishant analyze-bundles production-bundle \
     --project successful-show \
     --only-diff \
     --view tree
   ```

2. **Export Project Settings**
   ```bash
   # Document current project settings
   gishant analyze-bundles production-bundle \
     --project successful-show \
     --output project-overrides
   ```

3. **Preview Settings Lift**
   ```bash
   # Dry-run: lift project settings to studio defaults
   gishant sync-bundles \
     --operation project-bundle \
     --project successful-show \
     --bundle production-bundle \
     new-production-bundle \
     --dry-run
   ```

4. **Apply to Studio Defaults**
   ```bash
   # Lift project settings to new bundle
   gishant sync-bundles \
     --operation project-bundle \
     --project successful-show \
     --bundle production-bundle \
     new-production-bundle
   ```

5. **Verification**
   ```bash
   # Verify studio defaults updated
   gishant analyze-bundles new-production-bundle --view table

   # Verify project no longer has overrides
   gishant analyze-bundles new-production-bundle \
     --project successful-show \
     --only-diff
   ```

---

### Workflow 5: CI/CD Integration

**Scenario:** Automate bundle promotion in continuous deployment.

**Example GitHub Actions Workflow:**

```yaml
name: Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install gishant-scripts
        run: |
          pip install gishant-scripts
          pip install rdo-ayon-utils

      - name: Configure AYON
        env:
          AYON_SERVER_URL: ${{ secrets.AYON_SERVER_URL }}
          AYON_API_KEY: ${{ secrets.AYON_API_KEY }}
        run: |
          echo "AYON_SERVER_URL=$AYON_SERVER_URL" >> $GITHUB_ENV
          echo "AYON_API_KEY=$AYON_API_KEY" >> $GITHUB_ENV

      - name: Dry-run sync
        run: |
          gishant sync-bundles dev-bundle staging-bundle \
            --sync-mode diff-only \
            --dry-run \
            --force

      - name: Deploy to staging
        run: |
          gishant sync-bundles dev-bundle staging-bundle \
            --sync-mode diff-only \
            --force 2>&1 | tee deploy.log

      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: deployment-logs
          path: deploy.log

      - name: Notify on failure
        if: failure()
        run: |
          # Send notification (Slack, email, etc.)
          echo "Deployment failed!"
```

**Production Deployment (Manual Approval):**

```yaml
name: Deploy to Production

on:
  workflow_dispatch:  # Manual trigger only

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production  # Requires approval
    steps:
      - name: Deploy to production
        run: |
          gishant sync-bundles staging-bundle production-bundle \
            --sync-mode diff-only \
            --force
```



## Safety Features

### 1. Dry-Run Mode

Always use `--dry-run` first to preview changes:

```bash
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --dry-run
```

**Benefits:**
- See exactly what will change
- No modifications to AYON server
- Verify settings before applying
- Safe for testing and validation

### 2. Automatic Backups

Before any sync operation, the tool automatically creates backups:

**Backup Location:** `~/.ayon/sync_backups/`

**Backup Format:**
```
~/.ayon/sync_backups/
  └── bundle-to-bundle_staging-v1.1.0_20240115_143022/
      ├── metadata.json
      ├── studio_settings.json
      ├── project_settings.json
      ├── anatomy.json
      └── addon_versions.json
```

**Metadata Example:**
```json
{
  "timestamp": "2024-01-15T14:30:22",
  "operation": "bundle-to-bundle",
  "source": "production-v1.0.0",
  "target": "staging-v1.1.0",
  "user": "gishant"
}
```

### 3. Rollback Capability

If a sync fails or produces unexpected results, rollback from backup:

```python
from gishant_scripts.ayon.sync_bundles import restore_from_backup

restore_from_backup(
    backup_path="/home/user/.ayon/sync_backups/bundle-to-bundle_staging_20240115_143022",
    target="staging-v1.1.0"
)
```

### 4. Confirmation Prompts

Interactive confirmations prevent accidental changes:

```
⚠️  Warning: This will modify 'staging-v1.1.0' bundle settings.

Changes Summary:
  • Studio Settings: 3 changes
  • Project Settings: 5 changes
  • Addons: 2 version updates
  • Anatomy: 1 change

Backup will be created at: ~/.ayon/sync_backups/bundle-to-bundle_staging_20240115_143022

Proceed with sync? [y/N]:
```

Use `--force` to skip in automated scenarios.

### 5. Error Handling

The tool handles errors gracefully:

```
✗ Error: Failed to sync studio settings
  Reason: Connection timeout to AYON server

Rollback initiated...
✓ Successfully restored from backup

No changes were applied.
```

## Best Practices

### 1. Always Dry-Run First

```bash
# DON'T do this first
gishant sync-bundles source target --operation bundle-to-bundle

# DO this first
gishant sync-bundles source target --operation bundle-to-bundle --dry-run

# Then apply
gishant sync-bundles source target --operation bundle-to-bundle
```

### 2. Use Diff Mode for Safety

```bash
# Sync only differences (safer)
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --sync-mode diff

# Avoid syncing all unless necessary
# --sync-mode all
```

### 3. Analyze Before Syncing

```bash
# Step 1: Understand differences
gishant analyze-bundles bundle1 bundle2 --verbose

# Step 2: Sync based on analysis
gishant sync-bundles bundle1 bundle2 \
  --operation bundle-to-bundle \
  --sync-mode diff
```

### 4. Sync Specific Addons When Possible

```bash
# Instead of syncing everything
gishant sync-bundles source target --operation bundle-to-bundle

# Sync only what changed
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --addon maya
```

### 5. Verify Backups Exist

```bash
# Check backup directory before major sync
ls -la ~/.ayon/sync_backups/

# After sync, verify backup was created
ls -la ~/.ayon/sync_backups/ | tail -n 1
```

### 6. Use Descriptive Bundle Names

```bash
# Good bundle names
production-v1.0.0
staging-v1.1.0-rc1
dev-maya-update-2024-01

# Avoid generic names
bundle1
test
latest
```

### 7. Document Sync Operations

```bash
# Log sync operations for audit trail
gishant sync-bundles prod-v1 prod-v2 \
  --operation bundle-to-bundle \
  --sync-mode diff 2>&1 | tee sync-prod-v1-to-v2.log
```

### 8. Test with Non-Critical Bundles First

```bash
# Test sync process on dev bundles
gishant sync-bundles dev-test1 dev-test2 \
  --operation bundle-to-bundle

# Then apply to production
gishant sync-bundles prod-v1 prod-v2 \
  --operation bundle-to-bundle
```

### 9. Interactive Mode for Complex Syncs

```bash
# For complex multi-addon syncs, use interactive
gishant sync-bundles --interactive
```

### 10. Regular Bundle Audits

```bash
# Weekly comparison of prod vs staging
gishant analyze-bundles production staging \
  --output json \
  --save reports/bundle-comparison-$(date +%Y%m%d).json
```

## Troubleshooting

### Connection Issues

**Problem:** "Failed to connect to AYON server"

**Solutions:**
```bash
# Check AYON server is running
curl http://ayon-server:5000/api/info

# Verify credentials
export AYON_SERVER_URL="http://your-server:5000"
export AYON_API_KEY="your-api-key"

# Test connection
python -c "import ayon_api; print(ayon_api.get_bundles())"
```

### Permission Errors

**Problem:** "Insufficient permissions to modify bundle"

**Solutions:**
- Ensure your API key has admin permissions
- Check bundle is not locked
- Verify you're not trying to modify production bundle without proper access

### Backup Restore Failures

**Problem:** "Failed to restore from backup"

**Solutions:**
```bash
# Check backup integrity
ls -la ~/.ayon/sync_backups/your-backup-dir/

# Verify all required files exist
cat ~/.ayon/sync_backups/your-backup-dir/metadata.json

# Manual restore (if needed)
# Contact AYON administrator
```

### Sync Conflicts

**Problem:** "Conflicting settings detected during sync"

**Solutions:**
```bash
# Use dry-run to identify conflicts
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --dry-run \
  --verbose

# Resolve conflicts manually, then sync specific categories
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --addon maya  # Sync addon-by-addon
```

### Large Sync Timeouts

**Problem:** "Sync operation timed out"

**Solutions:**
```bash
# Sync in smaller chunks
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --addon maya

gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --addon nuke

# Or sync only differences
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --sync-mode diff
```

### Debugging

Enable verbose output:

```bash
# Set debug environment variable
export GISHANT_DEBUG=1

# Run with verbose logging
gishant sync-bundles source target \
  --operation bundle-to-bundle \
  --dry-run 2>&1 | tee debug.log
```

## Advanced Usage

### Programmatic Access

You can use these tools programmatically in your Python scripts:

```python
from gishant_scripts.ayon.sync_bundles import (
    sync_bundles,
    preview_sync_changes,
    create_backup
)
from gishant_scripts.ayon.analyze_bundles import compare_bundles

# Analyze bundles
differences = compare_bundles("bundle1", "bundle2")

# Preview changes
preview_sync_changes(
    source="bundle1",
    target="bundle2",
    operation="bundle-to-bundle",
    differences=differences,
    addons=["maya", "nuke"]
)

# Create backup
backup_path = create_backup(target="bundle2", operation="bundle-to-bundle")

# Perform sync
sync_bundles(
    source="bundle1",
    target="bundle2",
    sync_mode="diff",
    dry_run=False,
    addons=["maya"]
)
```

### Custom Filtering

Filter settings with custom logic:

```python
from gishant_scripts.ayon.analyze_bundles import get_differences

# Get all differences
all_diffs = get_differences("bundle1", "bundle2")

# Filter for specific settings
maya_settings = {
    k: v for k, v in all_diffs.items()
    if "maya" in k.lower()
}

# Apply custom sync logic
# ...
```

## Support

For issues, questions, or feature requests:

1. Check this documentation
2. Review [AYON Documentation](https://docs.ayon.dev/)
3. Contact pipeline team
4. Report bugs to gishant-scripts repository

## License

These tools are part of the gishant-scripts package and follow the same license.

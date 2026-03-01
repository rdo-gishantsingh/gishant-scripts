# Gishant's Custom Scripts

Collection of custom scripts for AYON pipeline, YouTrack integration, GitHub automation, and Maya/Unreal utilities.

## Overview

This repository contains personal utility scripts for:
- **YouTrack Integration**: Fetch and analyze issues
- **GitHub Automation**: PR fetching and analysis
- **Report Generation**: Automated work summaries using AI
- **Maya Utilities**: Mesh optimization, namespace fixes, attribute queries
- **Unreal Integration**: FBX imports, SM auto-assignment, benchmarking
- **AYON Tools**: Product management and bundle checking
- **Bulk Data Management**: Generate and clean test data for AYON and Kitsu (NEW! 🎉)

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for package management.

### Install uv (if not already installed)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Install the package
```bash
# Clone the repository
git clone https://github.com/yourusername/gishant-scripts.git
cd gishant-scripts

# Install dependencies and package (creates venv automatically)
uv sync
```

## Configuration

Create a `.env` file in the root directory with your credentials:

```bash
# YouTrack
YOUTRACK_URL=https://your-instance.youtrack.cloud
YOUTRACK_TOKEN=your-permanent-token

# GitHub (uses gh CLI, no token needed)
# Install: https://cli.github.com/

# Google AI (for report generation)
GOOGLE_API_KEY=your-google-ai-api-key

# AYON (for bulk data management)
AYON_SERVER_URL_LOCAL=http://localhost:5000
AYON_API_KEY_LOCAL=your-ayon-api-key

# Kitsu (for bulk data management)
KITSU_API_URL_LOCAL=http://localhost:8080/api
KITSU_LOGIN_LOCAL=admin@example.com
KITSU_PASSWORD_LOCAL=your-password
```

## Usage

### Command-Line Tools

After installation, use `uv run` to execute commands:

```bash
# Fetch YouTrack issues
uv run fetch-youtrack

# Fetch GitHub PRs
uv run fetch-github-prs

# Generate management report
uv run generate-report

# Generate work summary email
uv run generate-work-summary

# Compare AYON bundles
uv run gishant analyze-bundles --interactive

# Bulk data management for AYON and Kitsu
source .venv/bin/activate
bulk-data reset-and-generate --projects 2 --sequences 10 --shots 10 --yes

# Publish test asset (Bollywoof/test episode only; requires ffmpeg)
uv run publish-test-asset --dry-run
uv run publish-test-asset --folder-path /test
```

### Python Scripts

You can also import and use modules directly:

```python
from gishant_scripts.youtrack.fetch_issues import YouTrackIssuesFetcher
from gishant_scripts.github.fetch_prs import GitHubPRFetcher

# Use the modules...
```

## Scripts Overview

### YouTrack Integration
- **`fetch_issues.py`**: Fetch all YouTrack issues where you're involved (assigned or commented)
- Output: `my_youtrack_issues.json`, `my_youtrack_issue_ids.txt`

### GitHub Integration
- **`fetch_prs.py`**: Fetch GitHub PRs where you're author or assignee
- Requires: GitHub CLI (`gh`) installed and authenticated
- Output: `my_github_prs.json`

### Report Generation
- **`generate_report.py`**: Generate management-ready reports from YouTrack/GitHub data
- **`generate_work_summary.py`**: Create email summaries using Google Gemini AI
- Formats: Bullet points (audit-style) or paragraphs (executive-style)

### Maya Utilities
- **`benchmark_mesh_optimization.py`**: Benchmark mesh reduction performance
- **`create_unknown_nodes_and_plugins_maya.py`**: Create test scenes with unknown nodes
- **`createAndCheckIntermediateShapes.py`**: Manage intermediate shapes
- **`fix_namespace.py`**: Clean up namespace issues
- **`queryMayaAttributes.py`**: Query and analyze Maya attributes

### Unreal Utilities
- **`autoassign_sm.py`**: Auto-assign static meshes to actors
- **`maya_fbx_triangulate.py`**: Triangulate meshes for FBX export
- **`reload_libs.py`**: Hot-reload Python libraries in Unreal
- **`unreal_benchmark_fbxsm_import.py`**: Benchmark FBX static mesh import

### AYON/Pipeline Utilities
- **`ayon_products.py`**: Manage AYON products
- **`check_bundles.py`**: Check AYON bundle configurations
- **`kitsu_integration_demo.py`**: Kitsu integration examples
- **`search_executable.py`**: Find executables in system PATH
- **`publish-test-asset`**: Publish a test movie to AYON with Kitsu linking (Bollywoof/test episode only; safeguards enforced)

### Bulk Data Management (NEW! 🎉)
Unified tool for managing test data across AYON and Kitsu systems.

**Quick Start:**
```bash
source .venv/bin/activate

# Clean up and generate fresh data (one command!)
bulk-data reset-and-generate \
  --projects 2 \
  --sequences 10 \
  --shots 10 \
  --tasks 3 \
  --users 5 \
  --yes

# Or use the shell script
scripts/reset-and-populate.sh
```

**Features:**
- ✅ Clean up test data from both AYON and Kitsu
- ✅ Generate realistic bulk data with production naming conventions
- ✅ Dry-run mode to preview changes safely
- ✅ Progress bars and beautiful console output
- ✅ Handles errors gracefully
- ✅ Can target individual systems (--ayon-only, --kitsu-only)

**Commands:**
```bash
bulk-data cleanup --dry-run              # Preview what will be deleted
bulk-data cleanup --yes                  # Delete all test data
bulk-data generate -p 2 -s 10 --shots 10 # Generate data only
bulk-data reset-and-generate --yes       # Clean + generate (recommended)
```

**Documentation:**
- **Quick Start:** [QUICK_START_BULK_DATA.md](QUICK_START_BULK_DATA.md)
- **Full Guide:** [BULK_DATA_MANAGER_GUIDE.md](BULK_DATA_MANAGER_GUIDE.md)
- **Usage Summary:** [USAGE_SUMMARY.md](USAGE_SUMMARY.md)
- **Test Results:** [TEST_RESULTS.md](TEST_RESULTS.md)

### publish-test-asset (AYON-Kitsu linking test)
Publishes a minimal movie to AYON in **Bollywoof/test** with Kitsu linking for validating USER-319 / PIPE-523.

**Safeguards:** Only project `Bollywoof` and episode `test` are allowed. All target folders must be under that episode.

```bash
uv run publish-test-asset --dry-run           # Validate context only
uv run publish-test-asset                    # Publish to /test (generates placeholder)
uv run publish-test-asset -f /test/sq001/sh1 # Publish to a specific shot
uv run publish-test-asset --file ./video.mov # Use custom video file
```

**Requires:** ffmpeg (for placeholder), AYON + Kitsu credentials (~/.rdo/.env or env vars).

## Development

### Install with dev dependencies
```bash
uv sync --extra dev
```

### Run linting
```bash
uv run ruff check .
uv run ruff format .
```

### Run tests
```bash
uv run pytest
```

## Project Structure

```
gishant-scripts/
├── src/
│   └── gishant_scripts/
│       ├── __init__.py
│       ├── youtrack/       # YouTrack integration
│       ├── github/         # GitHub automation
│       ├── maya/           # Maya utilities
│       ├── unreal/         # Unreal utilities
│       └── utils/          # General utilities
├── tests/
├── .env                    # Your credentials (gitignored)
├── .gitignore
├── pyproject.toml
├── Makefile
└── README.md
```

## Makefile Commands

```bash
make install    # Install dependencies
make dev        # Install with dev dependencies
make format     # Format code with ruff
make lint       # Lint code with ruff
make test       # Run tests
make clean      # Clean build artifacts
```

## Notes

- **Security**: Never commit `.env` file - it contains sensitive credentials
- **GitHub CLI**: Some scripts require `gh` CLI to be installed and authenticated
- **Maya Scripts**: Must be run within Maya's Python environment
- **Unreal Scripts**: Must be run within Unreal Editor's Python environment

## License

Private repository - Internal use only

## Author

Gishant Singh - gisi@redefine.co

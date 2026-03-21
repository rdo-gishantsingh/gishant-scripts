# Gishant Scripts

Personal pipeline automation utilities for YouTrack, GitHub, AYON, Kitsu, BookStack, media conversion, and DCC diagnostics.

## Installation

Requires [uv](https://github.com/astral-sh/uv) and Python 3.11+.

```bash
git clone https://github.com/yourusername/gishant-scripts.git
cd gishant-scripts

# Install with dev dependencies (recommended)
uv sync --extra dev
```

Some dependencies (`ayon-python-api`, `gazu`) connect to RDO infrastructure and are only useful inside that environment. They are declared as direct deps but will install fine anywhere.

## Configuration

Set credentials as environment variables or in a `.env` file at the project root:

```bash
# YouTrack
YOUTRACK_URL=https://your-instance.youtrack.cloud
YOUTRACK_API_TOKEN=your-permanent-token

# GitHub
GITHUB_TOKEN=your-personal-access-token   # optional if gh CLI is authenticated

# Google AI (Gemini, used by youtrack summary)
GOOGLE_AI_API_KEY=your-google-ai-api-key

# BookStack
BOOKSTACK_URL=https://your-bookstack-instance
BOOKSTACK_TOKEN_ID=your-token-id
BOOKSTACK_TOKEN_SECRET=your-token-secret

# AYON (optional, for ayon subcommand)
AYON_SERVER_URL=http://localhost:5000
AYON_API_KEY=your-ayon-api-key

# Kitsu (optional, for kitsu subcommand)
KITSU_API_URL_LOCAL=http://localhost:8080/api
KITSU_LOGIN_LOCAL=admin@example.com
KITSU_PASSWORD_LOCAL=your-password
```

## CLI Usage

All commands live under the `gishant` entry point:

```bash
uv run gishant --help
```

### Subcommands

| Command | Description |
|---------|-------------|
| `gishant youtrack fetch` | Fetch YouTrack issues (all or by ID) |
| `gishant youtrack create` | Create a new YouTrack issue |
| `gishant youtrack update` | Update an existing issue |
| `gishant youtrack summary` | Generate a work summary using Gemini AI |
| `gishant github fetch-prs` | Fetch GitHub PRs assigned to you |
| `gishant media convert` | Convert media files using FFmpeg presets |
| `gishant media presets` | List available conversion presets |
| `gishant media info` | Display media file information |
| `gishant media interactive` | Interactive preset selection |
| `gishant ayon list-projects` | List AYON projects (supports `--local`/`--dev` flags) |
| `gishant kitsu list-projects` | List Kitsu projects |
| `gishant bookstack search` | Search BookStack documentation |
| `gishant bookstack pages/books/chapters/shelves` | Manage BookStack content |
| `gishant task-workspace new` | Create worktrees + VS Code workspace for an issue |
| `gishant task-workspace adopt` | Adopt existing checkouts into a workspace |
| `gishant task-workspace cleanup` | Remove a task workspace and its worktrees |

### Examples

```bash
gishant youtrack fetch
gishant youtrack summary --weeks 4
gishant github fetch-prs --limit 50
gishant media convert input.mov -p web-video
gishant bookstack search 'render pipeline'
gishant task-workspace new PIPE-123
```

## Project Structure

```
gishant-scripts/
├── src/
│   └── gishant_scripts/
│       ├── cli.py              # Main Typer app and subcommand registration
│       ├── _core/              # Shared config, logging, decorators, errors
│       ├── ayon/               # AYON CRUD operations
│       ├── bookstack/          # BookStack API client and CLI
│       ├── diagnostic/         # DCC diagnostic runners (Maya, Unreal, AYON env)
│       ├── github/             # GitHub PR fetching
│       ├── kitsu/              # Kitsu CRUD operations
│       ├── media/              # FFmpeg media conversion with presets
│       ├── task_workspace/     # VS Code task-workspace generator
│       └── youtrack/           # YouTrack fetch, create, update, summary
├── scripts/                    # Standalone DCC scripts (not part of the package)
│   ├── maya/                   # Maya utilities (mesh benchmarks, namespace fixes)
│   ├── unreal/                 # Unreal utilities (SM auto-assign, FBX import)
│   ├── nuke/                   # Nuke diagnostic scripts
│   └── rez/                    # Rez package build helpers
├── tests/
├── .env                        # Credentials (gitignored)
├── pyproject.toml
├── Makefile
├── CHANGELOG.md
└── README.md
```

## Diagnostic Module

The `diagnostic` package runs Maya and Unreal through the AYON Launcher environment for artist-parity testing. Defaults can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAYA_BIN` | `/usr/autodesk/maya2025/bin/maya` | Path to Maya binary |
| `DIAGNOSTIC_SSH_HOST` | `gisi@10.1.68.205` | SSH target for remote Windows runs |
| `DIAGNOSTIC_BASE_DIR` | `/tech/users/gisi/dev/_diagnostic` | Output directory (Linux) |
| `DIAGNOSTIC_BASE_DIR_WIN` | `Z:\users\gisi\dev\_diagnostic` | Output directory (Windows) |
| `AYON_SERVER_URL` | `http://localhost:5000` | AYON server for diagnostic context |
| `AYON_SERVER_URL_WIN` | `http://10.1.69.24:5000` | AYON server (Windows side) |

## Development

```bash
make format     # Format code with ruff
make lint       # Lint and auto-fix with ruff
make lint-check # Lint without fixing
make test       # Run all tests
make test-unit  # Run unit tests only
make test-all   # Run all tests (ignore addopts)
make clean      # Remove caches and build artifacts
```

## Notes

- Never commit `.env` -- it contains sensitive credentials.
- Some GitHub commands require the `gh` CLI to be installed and authenticated.
- Scripts in `scripts/maya/` and `scripts/unreal/` must be run inside their respective DCC Python environments.

## License

Private repository -- internal use only.

## Author

Gishant Singh - gisi@redefine.co

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `youtrack summary` subcommand for generating work summaries with Gemini AI
- `bookstack` subcommand for managing BookStack documentation (search, pages, books, chapters, shelves, attachments, users)
- `task-workspace` subcommand for creating VS Code task workspaces from YouTrack issues (new, adopt, modify, cleanup, sync-settings)
- `ayon` subcommand for AYON CRUD operations (list/get/create/delete projects, list users) with `--local`/`--dev` environment flags
- `kitsu` subcommand for Kitsu CRUD operations (login, list/get/create/update projects)
- `media` subcommand with FFmpeg presets for video/audio conversion, file info, and interactive mode
- `diagnostic` module for running Maya and Unreal through AYON Launcher environment with env-var overrides
- `_core` package with shared config, logging, decorators, error handling, and Gemini integration
- Standalone DCC scripts under `scripts/` (maya, unreal, nuke, rez)

### Changed

- Restructured all CLI commands under a single `gishant` entry point with domain subcommands
- Moved shared configuration (YouTrack, GitHub, Google AI, BookStack credentials) into `_core/config.py`
- Corrected environment variable names: `YOUTRACK_API_TOKEN` (not `YOUTRACK_TOKEN`), `GOOGLE_AI_API_KEY` (not `GOOGLE_API_KEY`)

### Removed

- Removed standalone entry points (`fetch-youtrack`, `fetch-github-prs`, `generate-report`, `generate-work-summary`)
- Removed `utils/` package (functionality moved to `_core/` and domain packages)

### Fixed

- README.md rewritten to match actual codebase (correct env vars, CLI commands, project structure)
- Makefile cleaned up: removed dead targets, added test-unit/test-integration/test-all targets

## [0.1.0] - 2025-11-10

### Added

- Initial repository organization using uv package manager
- Organized project structure with proper Python package layout
- YouTrack integration for fetching and analyzing issues
- GitHub PR fetching via `gh` CLI
- Work summary generation using Google Gemini AI
- Maya utility scripts (mesh benchmarks, namespace fixes, attribute queries)
- Unreal utility scripts (SM auto-assign, FBX import benchmarks, lib reload)
- Comprehensive README.md with usage instructions
- Makefile with common development tasks
- Test infrastructure with pytest

### Dependencies

- requests: HTTP client for API interactions
- google-genai: Google Gemini AI for report generation
- python-dotenv: Environment variable management
- typer + rich: CLI framework with styled terminal output
- ayon-python-api: AYON server communication
- gazu: Kitsu API client

### Development

- ruff: Code formatting and linting
- pytest: Testing framework
- pytest-cov: Test coverage reporting

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- FFmpeg video conversion tools with 10 presets (web, mobile, archive, GIF, etc.)
- FFmpeg audio conversion tools with podcast and compression presets
- Rich library integration for beautiful terminal output across all commands
- Colored, styled CLI output with consistent formatting

### Changed

- **BREAKING**: Renamed commands for better organization:
  - `convert-video` → `ffmpeg-video`
  - `convert-audio` → `ffmpeg-audio`
  - `list-presets` → `list-ffmpeg-presets`
- Standardized all CLI output to use Rich Console with:
  - Green colored success messages
  - Red colored errors (routed to stderr)
  - Cyan colored progress indicators
  - Yellow colored warnings and hints
  - Dim styled secondary statistics
- Improved help text and command examples throughout

### Fixed

- Type checking issue with Google AI API key configuration
- Proper stderr routing for all error messages
- Trailing whitespace in CLI module

## [0.1.0] - 2025-11-10

### Added

- Initial repository organization using uv package manager
- Organized project structure with proper Python package layout
- Created modular structure with separate packages for:
  - `youtrack/`: YouTrack integration scripts
  - `github/`: GitHub automation and PR fetching
  - `maya/`: Maya utility scripts for pipeline work
  - `unreal/`: Unreal Engine integration utilities
  - `utils/`: General utilities and report generation
- Command-line entry points for common tasks:
  - `fetch-youtrack`: Fetch YouTrack issues
  - `fetch-github-prs`: Fetch GitHub pull requests
  - `generate-report`: Generate management reports
  - `generate-work-summary`: Generate work summary emails
- Comprehensive README.md with usage instructions
- Makefile with common development tasks
- Test infrastructure with pytest
- Proper .gitignore for Python/uv projects
- .env.example for credential configuration

### Scripts Included

- **YouTrack**: fetch_issues.py
- **GitHub**: fetch_prs.py
- **Reports**: generate_report.py, generate_work_summary.py
- **Maya**: benchmark_mesh_optimization.py, fix_namespace.py, queryMayaAttributes.py, and more
- **Unreal**: autoassign_sm.py, unreal_benchmark_fbxsm_import.py, reload_libs.py, and more
- **Utils**: ayon_products.py, check_bundles.py, kitsu_integration_demo.py, search_executable.py

### Dependencies

- requests: HTTP client for API interactions
- google-genai: Google Gemini AI for report generation
- python-dotenv: Environment variable management

### Development

- ruff: Code formatting and linting
- pytest: Testing framework
- pytest-cov: Test coverage reporting

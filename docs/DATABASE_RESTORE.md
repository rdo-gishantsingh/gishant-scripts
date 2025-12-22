# Database Restore Scripts

Modern Python CLI tools for restoring AYON and Kitsu PostgreSQL databases from backup files.

## Features

- ✨ **Beautiful TUI** with Rich progress bars and panels
- 🐳 **Docker Compose integration** for seamless container management
- 📦 **Multiple backup formats** (custom .dump/.backup, gzip .gz, plain SQL)
- 🔒 **Safety confirmations** with detailed warnings before destructive operations
- 🎯 **Auto-detection** of docker-compose.yml locations
- ⚡ **Progress tracking** for each restoration step
- 🛡️ **Robust error handling** with clear error messages

## Installation

```bash
# Install or update the package
cd /tech/users/gisi/dev/repos/gishant-scripts
uv pip install -e .
```

## Usage

### AYON Database Restore

```bash
# Basic usage (will prompt for confirmation)
restore-ayon-db /path/to/backup.dump

# Auto-confirm (skip prompt)
restore-ayon-db /path/to/backup.dump --yes

# Custom docker-compose.yml location
restore-ayon-db /path/to/backup.dump -f /custom/path/docker-compose.yml

# Custom database configuration
restore-ayon-db /path/to/backup.dump --db-name mydb --db-user myuser

# Via main CLI
gishant ayon restore-db /path/to/backup.dump

# Show help
restore-ayon-db --help
```

### Kitsu Database Restore

```bash
# Basic usage (will prompt for confirmation)
restore-kitsu-db /path/to/backup.dump

# Auto-confirm (skip prompt)
restore-kitsu-db /path/to/backup.dump --yes

# Skip schema upgrade step
restore-kitsu-db /path/to/backup.dump --skip-schema-upgrade

# Custom docker-compose.yml location
restore-kitsu-db /path/to/backup.dump -f /custom/path/docker-compose.yml

# Custom database configuration
restore-kitsu-db /path/to/backup.dump --db-name zoudb --db-user zou

# Via main CLI
gishant kitsu restore-db /path/to/backup.dump

# Show help
restore-kitsu-db --help
```

## Supported Backup Formats

The restore scripts automatically detect the backup format based on file extension:

1. **Custom Format** (`.dump`, `.backup`)
   - Uses `pg_restore` with `--no-owner --no-acl` flags
   - Most common format from `pg_dump -Fc`

2. **Gzip Compressed** (`.gz`)
   - Uses `zcat | psql` for decompression and restore
   - Suitable for compressed SQL dumps

3. **Plain SQL** (`.sql` or no extension)
   - Uses `psql` for direct SQL execution
   - Standard SQL dump format

## Restoration Process

Both AYON and Kitsu restore scripts follow this workflow:

1. **Pre-flight checks**
   - Verify Docker Compose is available
   - Check backup file exists
   - Display configuration summary

2. **Safety confirmation**
   - Show detailed warning about data loss
   - Require explicit confirmation (unless `--yes` flag used)

3. **Service management**
   - Stop application services (server/worker for AYON, zou/kitsu for Kitsu)
   - Ensure database service is running

4. **Database preparation**
   - Terminate active connections to database
   - Drop existing database
   - Create fresh database

5. **Data restoration**
   - Restore from backup using appropriate tool (pg_restore, zcat, psql)
   - Show progress with spinner

6. **Post-restore tasks**
   - **Kitsu only**: Run database schema upgrade via `zou upgrade-db`
   - Restart application services

7. **Completion**
   - Display success message
   - Confirm services are running

## Architecture

### Modular Design

```
common/
├── docker_utils.py      # Docker Compose wrapper functions
└── db_restore.py        # Core restore logic and workflow

ayon/
└── restore_db_cli.py    # AYON-specific CLI

kitsu/
└── restore_db_cli.py    # Kitsu-specific CLI
```

### Key Components

#### `docker_utils.py`
- `docker_compose_cmd()` - Execute docker compose commands
- `stop_services()` - Stop specified services
- `start_services()` - Start specified services
- `ensure_service_running()` - Ensure service is up
- `exec_in_service()` - Execute commands in containers
- `copy_to_container()` - Copy files to containers
- `detect_backup_format()` - Auto-detect backup format

#### `db_restore.py`
- `RestoreConfig` - Configuration dataclass
- `terminate_db_connections()` - Close active connections
- `drop_and_recreate_db()` - Reset database
- `restore_custom_format()` - Restore from pg_dump custom format
- `restore_gzip_format()` - Restore from gzip compressed SQL
- `restore_sql_format()` - Restore from plain SQL
- `run_schema_upgrade()` - Run post-restore schema upgrades
- `restore_database()` - Main orchestration function with progress

#### CLI Scripts
- Beautiful Rich panels for configuration display
- Typer for robust CLI argument handling
- Safety confirmations before destructive operations
- Auto-detection of docker-compose.yml locations
- Comprehensive help text and examples

## Differences from Bash Scripts

### Improvements

1. **Better UX**
   - Rich progress bars instead of echo statements
   - Beautiful panels for configuration and status
   - Color-coded output with consistent styling

2. **Type Safety**
   - Typer provides automatic validation
   - Type hints throughout codebase
   - Clear configuration dataclasses

3. **Error Handling**
   - Structured exceptions with context
   - Clear error messages with suggestions
   - Graceful degradation where appropriate

4. **Maintainability**
   - Shared utilities between AYON and Kitsu
   - Clear separation of concerns
   - Testable pure functions
   - Well-documented with docstrings

5. **Integration**
   - Works with existing gishant CLI framework
   - Can be imported as Python modules
   - Reusable across projects

### Backward Compatibility

The new Python scripts maintain feature parity with the original bash scripts:

- Same default values for database names and users
- Same service management behavior
- Same backup format detection logic
- Same pg_restore flags (`--no-owner --no-acl`)
- Same error tolerance (e.g., allowing pg_restore warnings)

## Configuration

### Auto-detection

Both CLIs automatically detect `docker-compose.yml` from their script locations:

- **AYON**: `src/gishant_scripts/ayon/ayon-server/docker-compose.yml`
- **Kitsu**: `src/gishant_scripts/kitsu/kitsu-server/docker-compose.yml`

### Custom Configuration

Override defaults using CLI options:

```bash
# Custom compose file location
--compose-file /path/to/docker-compose.yml

# Custom database credentials
--db-service db
--db-user myuser
--db-name mydb
```

## Error Handling

The scripts handle various error scenarios:

- **Docker not available**: Clear message to install Docker Compose
- **Compose file not found**: Prompt to specify location with `--compose-file`
- **Backup file not found**: Immediate validation failure
- **Service failures**: Docker Compose errors with stderr output
- **Database errors**: PostgreSQL errors from psql/pg_restore

## Examples

### Complete AYON Restore

```bash
# 1. Ensure Docker services are running
cd /tech/users/gisi/dev/repos/ayon-docker
docker compose ps

# 2. Run restore
restore-ayon-db ~/backups/ayon-prod-2024-12-20.dump

# Output:
# ╭─ ⚙️  Configuration ─╮
# │ Backup file: ayon-prod-2024-12-20.dump
# │ Database: ayon (user: ayon)
# │ Service: db
# ╰──────────────────────╯
#
# ╭─ ⚠️  Confirmation Required ─╮
# │ WARNING: This will:
# │   • Stop AYON server and worker services
# │   • Drop and recreate the database
# │   • Restore from: ayon-prod-2024-12-20.dump
# │   • Restart AYON services
# │
# │ All existing data will be permanently lost!
# ╰──────────────────────────────╯
# Do you want to continue? [y/N]: y
#
# ⠋ Stopping server, worker...
# ✓ Stopped server, worker
# ⠋ Ensuring db is running...
# ✓ db is running
# ⠋ Terminating active connections...
# ✓ Terminated active connections
# ⠋ Recreating database...
# ✓ Database recreated
# ⠋ Restoring from ayon-prod-2024-12-20.dump (custom)...
# ✓ Restored from ayon-prod-2024-12-20.dump
# ⠋ Starting server, worker...
# ✓ Started server, worker
#
# ╭─ ✨ Success ─╮
# │ ✓ Database restore completed successfully!
# │
# │ AYON server and worker services have been restarted.
# ╰───────────────╯
```

### Complete Kitsu Restore with Schema Upgrade

```bash
# 1. Ensure Docker services are running
cd /tech/users/gisi/dev/repos/kitsu-docker
docker compose ps

# 2. Run restore
restore-kitsu-db ~/backups/kitsu-staging-2024-12-20.dump --yes

# Output:
# ╭─ 🎬 Configuration ─╮
# │ Backup file: kitsu-staging-2024-12-20.dump
# │ Database: zoudb (user: zou)
# │ Service: db
# │ Schema upgrade: Enabled
# ╰─────────────────────╯
#
# ⠋ Stopping zou, kitsu...
# ✓ Stopped zou, kitsu
# ⠋ Ensuring db is running...
# ✓ db is running
# ⠋ Terminating active connections...
# ✓ Terminated active connections
# ⠋ Recreating database...
# ✓ Database recreated
# ⠋ Restoring from kitsu-staging-2024-12-20.dump (custom)...
# ✓ Restored from kitsu-staging-2024-12-20.dump
# ⠋ Upgrading database schema...
# ✓ Database schema upgraded
# ⠋ Starting zou, kitsu...
# ✓ Started zou, kitsu
#
# ╭─ ✨ Success ─╮
# │ ✓ Database restore completed successfully!
# │
# │ Kitsu application and frontend services have been restarted.
# ╰───────────────╯
```

## Troubleshooting

### Docker Compose Not Found

```bash
# Error: docker compose not found
# Solution: Install Docker with Compose plugin
# https://docs.docker.com/compose/install/
```

### Compose File Not Found

```bash
# Error: Could not find docker-compose.yml
# Solution: Specify path explicitly
restore-ayon-db backup.dump -f /path/to/docker-compose.yml
```

### Permission Denied

```bash
# Error: Permission denied accessing backup file
# Solution: Check file permissions
chmod +r backup.dump
```

### Database Connection Refused

```bash
# Error: Connection refused to database service
# Solution: Ensure database service is running
docker compose ps
docker compose start db
```

## Development

### Running Tests

```bash
cd /tech/users/gisi/dev/repos/gishant-scripts
pytest tests/test_db_restore.py -v
```

### Code Quality

```bash
# Format with Ruff
ruff format src/

# Lint with Ruff
ruff check src/

# Type check (if mypy is added)
mypy src/
```

## Migration from Bash Scripts

The original bash scripts are still available at:
- `src/gishant_scripts/ayon/ayon-server/restore-db.sh`
- `src/gishant_scripts/kitsu/kitsu-server/restore-db.sh`

To migrate to the new Python CLIs:

1. **Install the package** (if not already done)
   ```bash
   cd /tech/users/gisi/dev/repos/gishant-scripts
   uv pip install -e .
   ```

2. **Replace bash commands** with new CLI commands:
   ```bash
   # Before
   cd src/gishant_scripts/ayon/ayon-server
   ./restore-db.sh /path/to/backup.dump

   # After
   restore-ayon-db /path/to/backup.dump
   ```

3. **Update scripts/automation** that reference the bash scripts

4. **Deprecate bash scripts** once migration is complete

## License

Part of gishant-scripts package. See main project LICENSE.

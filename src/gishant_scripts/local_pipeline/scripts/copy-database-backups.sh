#!/bin/bash
# DEPRECATED: This script has been superseded by sync-and-restore-databases.sh
# which copies backups AND restores them in one step.
#
# Please update your cron entry to:
#   30 0 * * * /home/gisi/dev/repos/gishant-scripts/scripts/sync-and-restore-databases.sh >> /home/gisi/dev/backups/sync-restore.log 2>&1
#
# This file is kept so that any existing cron reference prints a warning
# rather than silently failing.

echo "[DEPRECATED] copy-database-backups.sh is no longer used."
echo "Use sync-and-restore-databases.sh instead (see cron comment at the top of that file)."
echo "Remove the old cron entry with: sudo crontab -e"
exit 0

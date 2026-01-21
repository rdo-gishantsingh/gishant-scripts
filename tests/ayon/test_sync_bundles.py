"""Tests for sync_bundles module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gishant_scripts.ayon.sync_bundles import (
    BackupError,
    RollbackError,
    SyncError,
    create_backup,
    preview_sync_changes,
    restore_from_backup,
    sync_addon_versions,
    sync_anatomy,
    sync_bundles,
    sync_project_settings,
    sync_project_to_bundle,
    sync_projects,
    sync_studio_settings,
)


class TestBackupOperations:
    """Tests for backup and restore operations."""

    def test_create_backup_bundle(self, mock_console, sample_studio_settings, temp_backup_dir, monkeypatch):
        """Test creating bundle settings backup."""
        monkeypatch.chdir(temp_backup_dir)

        backup_file = create_backup(
            "test-bundle",
            sample_studio_settings,
            "bundle",
            mock_console,
        )

        assert backup_file.exists()
        assert backup_file.suffix == ".json"
        assert "test-bundle" in backup_file.name
        assert "bundle" in backup_file.name

        # Verify backup content - implementation writes settings directly
        with open(backup_file) as f:
            data = json.load(f)
            assert data == sample_studio_settings

    def test_create_backup_project(self, mock_console, sample_project_settings, temp_backup_dir, monkeypatch):
        """Test creating project settings backup."""
        monkeypatch.chdir(temp_backup_dir)

        backup_file = create_backup(
            "test-bundle",
            sample_project_settings,
            "project",
            mock_console,
            project_name="test-project",
        )

        assert backup_file.exists()
        assert "test-project" in backup_file.name

        # Verify backup content - implementation writes settings directly
        with open(backup_file) as f:
            data = json.load(f)
            assert data == sample_project_settings

    def test_create_backup_anatomy(self, mock_console, sample_anatomy, temp_backup_dir, monkeypatch):
        """Test creating anatomy backup."""
        monkeypatch.chdir(temp_backup_dir)

        backup_file = create_backup(
            "test-bundle",
            sample_anatomy,
            "anatomy",
            mock_console,
            project_name="test-project",
        )

        assert backup_file.exists()

        # Verify backup content - implementation writes settings directly
        with open(backup_file) as f:
            data = json.load(f)
            assert data == sample_anatomy

    @patch("gishant_scripts.ayon.sync_bundles.Path.mkdir")
    def test_create_backup_failure(self, mock_mkdir, mock_console, sample_studio_settings):
        """Test backup creation failure handling."""
        # Mock mkdir to raise permission error
        mock_mkdir.side_effect = PermissionError("Permission denied")

        with pytest.raises(BackupError):
            create_backup("test-bundle", sample_studio_settings, "bundle", mock_console)

    def test_restore_from_backup_success(self, mock_console, temp_backup_dir):
        """Test successful backup restoration."""
        # Create a backup file
        backup_data = {
            "bundle_name": "test-bundle",
            "backup_type": "bundle",
            "settings": {"key": "value"},
            "timestamp": "2024-01-01T00:00:00",
        }
        backup_file = temp_backup_dir / "test_backup.json"
        with open(backup_file, "w") as f:
            json.dump(backup_data, f)

        result = restore_from_backup(backup_file, mock_console)

        assert result == backup_data
        assert result["settings"]["key"] == "value"

    def test_restore_from_backup_missing_file(self, mock_console, temp_backup_dir):
        """Test restore from non-existent backup."""
        backup_file = temp_backup_dir / "missing.json"

        with pytest.raises(RollbackError):
            restore_from_backup(backup_file, mock_console)

    def test_restore_from_backup_invalid_json(self, mock_console, temp_backup_dir):
        """Test restore from corrupted backup."""
        backup_file = temp_backup_dir / "corrupted.json"
        backup_file.write_text("invalid json content")

        with pytest.raises(RollbackError):
            restore_from_backup(backup_file, mock_console)


class TestPreviewSyncChanges:
    """Tests for sync preview functionality."""

    def test_preview_with_differences(self, mock_console):
        """Test preview display with differences."""
        differences = {
            "metadata": [{"key": "version", "bundle1": "1.0", "bundle2": "2.0"}],
            "addons": [{"addon": "maya", "bundle1": "1.0.0", "bundle2": "1.1.0"}],
            "settings": [{"path": "core.name", "bundle1": "Old", "bundle2": "New"}],
            "dependencies": [],
        }

        preview_sync_changes(
            differences,
            "source-bundle",
            "target-bundle",
            "diff-only",
            mock_console,
        )

        # Verify console was used for output
        assert mock_console.print.called

    def test_preview_with_addon_filter(self, mock_console):
        """Test preview with addon filter."""
        differences = {
            "metadata": [],
            "addons": [{"addon": "maya", "bundle1": "1.0.0", "bundle2": "1.1.0"}],
            "settings": [],
            "dependencies": [],
        }

        preview_sync_changes(
            differences,
            "source",
            "target",
            "diff-only",
            mock_console,
            addon_filter="maya",
        )

        assert mock_console.print.called

    def test_preview_no_changes(self, mock_console):
        """Test preview when no changes exist."""
        differences = {
            "metadata": [],
            "addons": [],
            "settings": [],
            "dependencies": [],
        }

        preview_sync_changes(differences, "source", "target", "all", mock_console)

        assert mock_console.print.called


class TestSyncAddonVersions:
    """Test sync_addon_versions function."""

    @pytest.fixture
    def dev_bundle_data(self):
        """Sample dev bundle data."""
        return {
            "name": "test-bundle-dev",
            "installerVersion": "1.0.0",
            "isProduction": False,
            "isStaging": False,
            "isDev": True,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-02T00:00:00Z",
            "addons": {
                "maya": "0.9.0",  # Older version than source
                "nuke": "2.0.0",  # Same as source
                "core": "2.9.0",  # Older version
            },
            "dependencyPackages": {
                "python": "3.11.0",
                "qt": "5.15.2",
            },
        }

    @pytest.fixture
    def non_dev_bundle_data(self):
        """Sample non-dev bundle (production) data."""
        return {
            "name": "test-bundle-prod",
            "installerVersion": "1.0.0",
            "isProduction": True,
            "isStaging": False,
            "isDev": False,
            "addons": {
                "maya": "0.9.0",
                "nuke": "2.0.0",
                "core": "2.9.0",
            },
        }

    def test_sync_addon_versions_success(self, mock_console, sample_bundle_data, dev_bundle_data, sample_bundles_data):
        """Test successful addon version sync with version differences."""
        with patch("gishant_scripts.ayon.sync_bundles.ayon_api") as mock_api:
            mock_con = MagicMock()
            mock_api.get_server_api_connection.return_value = mock_con

            # Mock fetch_all_bundles and get_bundle_by_name
            with patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles") as mock_fetch:
                with patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name") as mock_get:
                    mock_fetch.return_value = sample_bundles_data
                    mock_get.return_value = dev_bundle_data

                    result = sync_addon_versions(
                        source_bundle=sample_bundle_data,
                        target_bundle_name="test-bundle-dev",
                        console=mock_console,
                        dry_run=False,
                    )

                    # Should update maya (1.0.0 -> 0.9.0) and core (3.0.0 -> 2.9.0)
                    # nuke stays the same (2.0.0 == 2.0.0)
                    expected_updates = {
                        "maya": "1.0.0",
                        "core": "3.0.0",
                    }

                    mock_con.update_bundle.assert_called_once_with(
                        bundle_name="test-bundle-dev",
                        addon_versions=expected_updates,
                    )
                    assert result is True

    def test_sync_addon_versions_no_changes_needed(
        self, mock_console, sample_bundle_data, dev_bundle_data, sample_bundles_data
    ):
        """Test addon version sync when all versions already match."""
        # Make versions match
        dev_bundle_data["addons"] = sample_bundle_data["addons"].copy()

        with patch("gishant_scripts.ayon.sync_bundles.ayon_api") as mock_api:
            mock_con = MagicMock()
            mock_api.get_server_api_connection.return_value = mock_con

            with patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles") as mock_fetch:
                with patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name") as mock_get:
                    mock_fetch.return_value = sample_bundles_data
                    mock_get.return_value = dev_bundle_data

                    result = sync_addon_versions(
                        source_bundle=sample_bundle_data,
                        target_bundle_name="test-bundle-dev",
                        console=mock_console,
                        dry_run=False,
                    )

                    # No API call should be made when no updates needed
                    mock_con.update_bundle.assert_not_called()
                    assert result is True

    def test_sync_addon_versions_dry_run(self, mock_console, sample_bundle_data, dev_bundle_data, sample_bundles_data):
        """Test addon version sync in dry run mode."""
        with patch("gishant_scripts.ayon.sync_bundles.ayon_api") as mock_api:
            mock_con = MagicMock()
            mock_api.get_server_api_connection.return_value = mock_con

            with patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles") as mock_fetch:
                with patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name") as mock_get:
                    mock_fetch.return_value = sample_bundles_data
                    mock_get.return_value = dev_bundle_data

                    result = sync_addon_versions(
                        source_bundle=sample_bundle_data,
                        target_bundle_name="test-bundle-dev",
                        console=mock_console,
                        dry_run=True,
                    )

                    # In dry run, should not call API
                    assert result is True
                    mock_con.update_bundle.assert_not_called()

    def test_sync_addon_versions_with_filter(
        self, mock_console, sample_bundle_data, dev_bundle_data, sample_bundles_data
    ):
        """Test addon version sync with addon filter."""
        with patch("gishant_scripts.ayon.sync_bundles.ayon_api") as mock_api:
            mock_con = MagicMock()
            mock_api.get_server_api_connection.return_value = mock_con

            with patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles") as mock_fetch:
                with patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name") as mock_get:
                    mock_fetch.return_value = sample_bundles_data
                    mock_get.return_value = dev_bundle_data

                    result = sync_addon_versions(
                        source_bundle=sample_bundle_data,
                        target_bundle_name="test-bundle-dev",
                        console=mock_console,
                        dry_run=False,
                        addon_filter="maya",  # Only sync maya addon
                    )

                    # Should only update maya (filtered)
                    expected_updates = {"maya": "1.0.0"}

                    mock_con.update_bundle.assert_called_once_with(
                        bundle_name="test-bundle-dev",
                        addon_versions=expected_updates,
                    )
                    assert result is True

    def test_sync_addon_versions_non_dev_bundle_fails(
        self, mock_console, sample_bundle_data, non_dev_bundle_data, sample_bundles_data
    ):
        """Test addon version sync fails for non-dev bundle."""
        with patch("gishant_scripts.ayon.sync_bundles.ayon_api") as mock_api:
            mock_con = MagicMock()
            mock_api.get_server_api_connection.return_value = mock_con

            with patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles") as mock_fetch:
                with patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name") as mock_get:
                    mock_fetch.return_value = sample_bundles_data
                    mock_get.return_value = non_dev_bundle_data

                    with pytest.raises(SyncError) as exc_info:
                        sync_addon_versions(
                            source_bundle=sample_bundle_data,
                            target_bundle_name="test-bundle-prod",
                            console=mock_console,
                            dry_run=False,
                        )

                    assert "Only dev bundles" in str(exc_info.value)
                    # No API call should be made
                    mock_con.update_bundle.assert_not_called()

    def test_sync_addon_versions_missing_ayon_api(self, mock_console, sample_bundle_data):
        """Test addon version sync fails when ayon_api is not installed."""
        with patch("gishant_scripts.ayon.sync_bundles.ayon_api", None):
            with pytest.raises(SyncError) as exc_info:
                sync_addon_versions(
                    source_bundle=sample_bundle_data,
                    target_bundle_name="test-bundle-dev",
                    console=mock_console,
                    dry_run=False,
                )

            assert "ayon-python-api not installed" in str(exc_info.value)

    def test_sync_addon_versions_api_failure(
        self, mock_console, sample_bundle_data, dev_bundle_data, sample_bundles_data
    ):
        """Test addon version sync when API fails."""
        with patch("gishant_scripts.ayon.sync_bundles.ayon_api") as mock_api:
            # Simulate API failure
            mock_con = MagicMock()
            mock_con.update_bundle.side_effect = Exception("API Error")
            mock_api.get_server_api_connection.return_value = mock_con

            with patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles") as mock_fetch:
                with patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name") as mock_get:
                    mock_fetch.return_value = sample_bundles_data
                    mock_get.return_value = dev_bundle_data

                    with pytest.raises(SyncError) as exc_info:
                        sync_addon_versions(
                            source_bundle=sample_bundle_data,
                            target_bundle_name="test-bundle-dev",
                            console=mock_console,
                            dry_run=False,
                        )

                    assert "Failed to sync addon versions" in str(exc_info.value)


class TestSyncStudioSettings:
    """Tests for studio settings synchronization."""

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_studio_settings_success(self, mock_api, mock_console, sample_studio_settings):
        """Test successful studio settings sync."""
        differences = [{"path": "applications.maya.version", "bundle1": "2024", "bundle2": "2025"}]

        result = sync_studio_settings(
            sample_studio_settings,
            "target-bundle",
            differences,
            mock_console,
            dry_run=False,
        )

        assert result is True

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_studio_settings_dry_run(self, mock_api, mock_console, sample_studio_settings):
        """Test studio settings sync in dry-run mode."""
        differences = [{"path": "test.setting", "bundle1": "old", "bundle2": "new"}]

        result = sync_studio_settings(
            sample_studio_settings,
            "target-bundle",
            differences,
            mock_console,
            dry_run=True,
        )

        assert result is True
        assert not mock_api.put.called


class TestSyncProjectSettings:
    """Tests for project settings synchronization."""

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_project_settings_success(self, mock_api, mock_console, sample_project_settings):
        """Test successful project settings sync."""
        differences = [{"path": "maya.render_settings.arnold.sampling", "bundle1": 5, "bundle2": 10}]

        result = sync_project_settings(
            sample_project_settings,
            "target-bundle",
            "test-project",
            differences,
            mock_console,
            dry_run=False,
        )

        assert result is True

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_project_settings_with_addon_filter(self, mock_api, mock_console, sample_project_settings):
        """Test project settings sync with addon filter."""
        differences = [{"path": "maya.setting", "bundle1": "old", "bundle2": "new"}]

        result = sync_project_settings(
            sample_project_settings,
            "target-bundle",
            "test-project",
            differences,
            mock_console,
            dry_run=False,
            addon_filter="maya",
        )

        assert result is True


class TestSyncAnatomy:
    """Tests for anatomy synchronization."""

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_anatomy_success(self, mock_api, mock_console, sample_anatomy):
        """Test successful anatomy sync."""
        differences = [{"path": "templates.work", "bundle1": "old_path", "bundle2": "new_path"}]

        result = sync_anatomy(
            sample_anatomy,
            "test-project",
            differences,
            mock_console,
            dry_run=False,
        )

        assert result is True

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_anatomy_dry_run(self, mock_api, mock_console, sample_anatomy):
        """Test anatomy sync in dry-run mode."""
        differences = [{"path": "test", "bundle1": "old", "bundle2": "new"}]

        result = sync_anatomy(
            sample_anatomy,
            "test-project",
            differences,
            mock_console,
            dry_run=True,
        )

        assert result is True
        assert not mock_api.put.called


class TestSyncBundles:
    """Tests for main bundle synchronization."""

    @patch("gishant_scripts.ayon.sync_bundles.create_backup")
    @patch("gishant_scripts.ayon.sync_bundles.sync_addon_versions")
    @patch("gishant_scripts.ayon.sync_bundles.sync_studio_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_differences")
    @patch("gishant_scripts.ayon.sync_bundles.compare_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name")
    @patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles")
    def test_sync_bundles_success(
        self,
        mock_fetch,
        mock_get_bundle,
        mock_get_settings,
        mock_compare,
        mock_get_diff,
        mock_sync_studio,
        mock_sync_addons,
        mock_backup,
        mock_console,
        sample_bundle_data,
        sample_bundles_data,
        sample_studio_settings,
    ):
        """Test successful bundle synchronization."""
        # Setup mocks
        mock_fetch.return_value = sample_bundles_data
        mock_get_bundle.return_value = sample_bundle_data
        mock_get_settings.return_value = sample_studio_settings
        mock_compare.return_value = {"metadata": {}, "addons": {}, "settings": {}}
        mock_get_diff.return_value = {
            "metadata": [],
            "addons": [{"addon": "maya", "bundle1": "1.0", "bundle2": "1.1"}],
            "settings": [],
            "dependencies": [],
        }
        mock_sync_addons.return_value = True
        mock_sync_studio.return_value = True
        mock_backup.return_value = Path("/tmp/backup.json")

        result = sync_bundles(
            "source-bundle",
            "target-bundle",
            mock_console,
            sync_mode="diff-only",
            dry_run=False,
            force=True,
        )

        assert result is True
        assert mock_backup.called

    @patch("gishant_scripts.ayon.sync_bundles.get_differences")
    @patch("gishant_scripts.ayon.sync_bundles.compare_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name")
    @patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles")
    def test_sync_bundles_no_changes(
        self,
        mock_fetch,
        mock_get_bundle,
        mock_get_settings,
        mock_compare,
        mock_get_diff,
        mock_console,
        sample_bundle_data,
        sample_bundles_data,
        sample_studio_settings,
    ):
        """Test sync when no changes are detected."""
        mock_fetch.return_value = sample_bundles_data
        mock_get_bundle.return_value = sample_bundle_data
        mock_get_settings.return_value = sample_studio_settings
        mock_compare.return_value = {"metadata": {}, "addons": {}, "settings": {}}
        mock_get_diff.return_value = {
            "metadata": [],
            "addons": [],
            "settings": [],
            "dependencies": [],
        }

        result = sync_bundles(
            "source-bundle",
            "target-bundle",
            mock_console,
            force=True,
        )

        # Implementation returns True when no changes to sync
        assert result is True

    @patch("gishant_scripts.ayon.sync_bundles.Confirm.ask")
    @patch("gishant_scripts.ayon.sync_bundles.get_differences")
    @patch("gishant_scripts.ayon.sync_bundles.compare_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name")
    @patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles")
    def test_sync_bundles_user_cancellation(
        self,
        mock_fetch,
        mock_get_bundle,
        mock_get_settings,
        mock_compare,
        mock_get_diff,
        mock_confirm,
        mock_console,
        sample_bundle_data,
        sample_bundles_data,
        sample_studio_settings,
    ):
        """Test sync when user cancels confirmation."""
        mock_fetch.return_value = sample_bundles_data
        mock_get_bundle.return_value = sample_bundle_data
        mock_get_settings.return_value = sample_studio_settings
        mock_compare.return_value = {"metadata": {}, "addons": {}, "settings": {}}
        mock_get_diff.return_value = {
            "metadata": [],
            "addons": [{"addon": "maya", "bundle1": "1.0", "bundle2": "1.1"}],
            "settings": [],
            "dependencies": [],
        }
        mock_confirm.return_value = False

        result = sync_bundles(
            "source-bundle",
            "target-bundle",
            mock_console,
            dry_run=False,
            force=False,
        )

        assert result is False


class TestSyncProjectToBundle:
    """Tests for project-to-bundle synchronization."""

    @patch("gishant_scripts.ayon.sync_bundles.sync_studio_settings")
    @patch("gishant_scripts.ayon.sync_bundles.create_backup")
    @patch("gishant_scripts.ayon.sync_bundles.get_differences")
    @patch("gishant_scripts.ayon.sync_bundles.compare_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_project_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name")
    @patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles")
    def test_sync_project_to_bundle_success(
        self,
        mock_fetch,
        mock_get_bundle,
        mock_get_project,
        mock_get_bundle_settings,
        mock_compare,
        mock_get_diff,
        mock_backup,
        mock_sync_studio,
        mock_console,
        sample_bundles_data,
        sample_bundle_data,
        sample_project_settings,
        sample_studio_settings,
    ):
        """Test successful project-to-bundle sync."""
        mock_fetch.return_value = sample_bundles_data
        mock_get_bundle.return_value = sample_bundle_data
        mock_get_project.return_value = sample_project_settings
        mock_get_bundle_settings.return_value = sample_studio_settings
        mock_compare.return_value = {"metadata": {}, "addons": {}, "settings": {}}
        mock_get_diff.return_value = {
            "metadata": [],
            "addons": [],
            "settings": [{"path": "maya.setting", "bundle1": "old", "bundle2": "new"}],
            "dependencies": [],
        }
        mock_backup.return_value = Path("/tmp/backup.json")
        mock_sync_studio.return_value = True

        result = sync_project_to_bundle(
            "test-project",
            "source-bundle",
            "target-bundle",
            mock_console,
            force=True,
        )

        assert result is True


class TestSyncProjects:
    """Tests for project-to-project synchronization."""

    @patch("gishant_scripts.ayon.sync_bundles.sync_anatomy")
    @patch("gishant_scripts.ayon.sync_bundles.sync_project_settings")
    @patch("gishant_scripts.ayon.sync_bundles.create_backup")
    @patch("gishant_scripts.ayon.sync_bundles.get_differences")
    @patch("gishant_scripts.ayon.sync_bundles.compare_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_project_anatomy")
    @patch("gishant_scripts.ayon.sync_bundles.get_project_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name")
    @patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles")
    def test_sync_projects_success(
        self,
        mock_fetch,
        mock_get_bundle,
        mock_get_project,
        mock_get_anatomy,
        mock_compare,
        mock_get_diff,
        mock_backup,
        mock_sync_project,
        mock_sync_anatomy,
        mock_console,
        sample_bundles_data,
        sample_bundle_data,
        sample_project_settings,
        sample_anatomy,
    ):
        """Test successful project-to-project sync."""
        mock_fetch.return_value = sample_bundles_data
        mock_get_bundle.return_value = sample_bundle_data
        mock_get_project.return_value = sample_project_settings
        mock_get_anatomy.return_value = sample_anatomy
        mock_compare.return_value = {
            "metadata": {},
            "addons": {},
            "settings": {},
            "project_settings": {},
            "anatomy": {},
        }
        mock_get_diff.return_value = {
            "metadata": [],
            "addons": [],
            "settings": [],
            "project_settings": [{"path": "test", "bundle1": "old", "bundle2": "new"}],
            "anatomy": [],
            "dependencies": [],
        }
        mock_backup.return_value = Path("/tmp/backup.json")
        mock_sync_project.return_value = True
        mock_sync_anatomy.return_value = True

        result = sync_projects(
            "source-project",
            "target-project",
            "test-bundle",
            mock_console,
            force=True,
        )

        assert result is True


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error scenarios."""

    def test_create_backup_with_special_characters(
        self, mock_console, sample_studio_settings, temp_backup_dir, monkeypatch
    ):
        """Test backup creation with special characters in names."""
        monkeypatch.chdir(temp_backup_dir)

        backup_file = create_backup(
            "bundle-name-with-special@chars#123",
            sample_studio_settings,
            "bundle",
            mock_console,
        )

        assert backup_file.exists()

    @patch("gishant_scripts.ayon.sync_bundles.ayon_api")
    def test_sync_with_empty_addons(self, mock_api, mock_console):
        """Test sync with empty addon list."""
        bundle_data = {"name": "test", "addons": {}}

        result = sync_addon_versions(bundle_data, "target", mock_console, dry_run=True)

        assert result is True

    def test_preview_with_all_categories_empty(self, mock_console):
        """Test preview when all categories are empty."""
        differences = {
            "metadata": [],
            "addons": [],
            "settings": [],
            "dependencies": [],
            "project_settings": [],
            "anatomy": [],
        }

        # Should not raise exception
        preview_sync_changes(differences, "s", "t", "all", mock_console)

    @patch("gishant_scripts.ayon.sync_bundles.sync_addon_versions")
    @patch("gishant_scripts.ayon.sync_bundles.create_backup")
    @patch("gishant_scripts.ayon.sync_bundles.get_differences")
    @patch("gishant_scripts.ayon.sync_bundles.compare_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_settings")
    @patch("gishant_scripts.ayon.sync_bundles.get_bundle_by_name")
    @patch("gishant_scripts.ayon.sync_bundles.fetch_all_bundles")
    def test_sync_bundles_rollback_on_error(
        self,
        mock_fetch,
        mock_get_bundle,
        mock_get_settings,
        mock_compare,
        mock_get_diff,
        mock_backup,
        mock_sync_addons,
        mock_console,
        sample_bundles_data,
        sample_bundle_data,
        sample_studio_settings,
    ):
        """Test rollback when sync fails."""
        mock_fetch.return_value = sample_bundles_data
        mock_get_bundle.return_value = sample_bundle_data
        mock_get_settings.return_value = sample_studio_settings
        mock_compare.return_value = {"metadata": {}, "addons": {}, "settings": {}}
        mock_get_diff.return_value = {
            "metadata": [],
            "addons": [{"addon": "maya", "bundle1": "1.0", "bundle2": "1.1"}],
            "settings": [],
            "dependencies": [],
        }
        mock_backup.return_value = Path("/tmp/backup.json")
        mock_sync_addons.side_effect = SyncError("Sync failed")

        # sync_bundles catches SyncError and returns False instead of raising
        result = sync_bundles(
            "source-bundle",
            "target-bundle",
            mock_console,
            force=True,
        )
        assert result is False

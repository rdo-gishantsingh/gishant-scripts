"""Tests for analyze_bundles module."""

import json
from unittest.mock import patch

import pytest

from gishant_scripts.ayon.analyze_bundles import (
    AYONConnectionError,
    BundleNotFoundError,
    compare_settings,
    export_to_json,
    export_to_markdown,
    fetch_all_bundles,
    flatten_dict,
    get_all_projects,
    get_bundle_by_name,
    get_bundle_settings,
    get_differences,
    get_project_anatomy,
    get_project_settings,
    setup_ayon_connection,
)


class TestSetupAYONConnection:
    """Tests for AYON connection setup."""

    def test_setup_with_rdo_ayon_utils(self, mock_console, mock_rdo_ayon_utils):
        """Test successful setup using rdo-ayon-utils."""
        mock_rdo_ayon_utils.set_connection.return_value = None

        setup_ayon_connection(mock_console)

        mock_rdo_ayon_utils.set_connection.assert_called_once()

    def test_setup_without_utils_with_env(self, mock_console, mock_ayon_api, monkeypatch):
        """Test connection setup using environment variables."""
        # Set env variables
        monkeypatch.setenv("AYON_SERVER_URL", "http://test:5000")
        monkeypatch.setenv("AYON_API_KEY", "test-key")

        # Mock the modules as None
        import sys

        if "rdo_ayon_utils" in sys.modules:
            del sys.modules["rdo_ayon_utils"]

        setup_ayon_connection(mock_console)

        # Should have attempted connection
        assert mock_console.print.called

    def test_setup_without_credentials_raises_error(self, mock_console, mock_ayon_api, monkeypatch):
        """Test that setup raises error when credentials are not configured."""
        # Simulate missing rdo-ayon-utils
        import gishant_scripts.ayon.analyze_bundles as ab

        ab.ayon_utils = None

        # Ensure environment variables are not set
        monkeypatch.delenv("AYON_SERVER_URL", raising=False)
        monkeypatch.delenv("AYON_API_KEY", raising=False)

        with pytest.raises(AYONConnectionError, match="AYON connection not configured"):
            setup_ayon_connection(mock_console)


class TestFlattenDict:
    """Tests for dictionary flattening utility."""

    def test_flatten_simple_dict(self):
        """Test flattening a simple dictionary."""
        data = {"a": 1, "b": 2}
        result = flatten_dict(data)
        assert result == {"a": 1, "b": 2}

    def test_flatten_nested_dict(self):
        """Test flattening nested dictionaries."""
        data = {"level1": {"level2": {"level3": "value"}}}
        result = flatten_dict(data)
        assert result == {"level1.level2.level3": "value"}

    def test_flatten_with_max_depth(self):
        """Test flattening with maximum depth limit."""
        data = {"level1": {"level2": {"level3": "value"}}}
        result = flatten_dict(data, max_depth=1)
        assert "level1.level2" in result
        assert result["level1.level2"] == {"level3": "value"}

    def test_flatten_mixed_types(self):
        """Test flattening with mixed value types."""
        data = {
            "string": "value",
            "number": 42,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
        }
        result = flatten_dict(data)
        assert result["string"] == "value"
        assert result["number"] == 42
        assert result["list"] == [1, 2, 3]
        assert result["nested.key"] == "value"

    def test_flatten_with_custom_separator(self):
        """Test flattening with custom separator."""
        data = {"a": {"b": "value"}}
        result = flatten_dict(data, sep="/")
        assert result == {"a/b": "value"}


class TestBundleOperations:
    """Tests for bundle-related operations."""

    def test_fetch_all_bundles_success(self, mock_console, mock_ayon_api, sample_bundles_data):
        """Test successful fetching of all bundles."""
        mock_ayon_api.get_bundles.return_value = sample_bundles_data

        result = fetch_all_bundles(mock_console)

        assert result == sample_bundles_data
        mock_ayon_api.get_bundles.assert_called_once()

    def test_fetch_all_bundles_failure(self, mock_console, mock_ayon_api):
        """Test handling of fetch failure."""
        mock_ayon_api.get_bundles.side_effect = Exception("Connection error")

        with pytest.raises(AYONConnectionError, match="Failed to fetch bundles"):
            fetch_all_bundles(mock_console)

    def test_get_bundle_by_name_found(self, sample_bundles_data):
        """Test getting bundle by name when it exists."""
        result = get_bundle_by_name(sample_bundles_data, "test-bundle-1.0")

        assert result["name"] == "test-bundle-1.0"
        assert result["isProduction"] is True

    def test_get_bundle_by_name_not_found(self, sample_bundles_data):
        """Test getting bundle by name when it doesn't exist."""
        with pytest.raises(BundleNotFoundError, match="Bundle 'nonexistent' not found"):
            get_bundle_by_name(sample_bundles_data, "nonexistent")

    @patch("gishant_scripts.ayon.analyze_bundles.ayon_api")
    def test_get_bundle_settings_success(self, mock_ayon_api, mock_console, sample_studio_settings):
        """Test successful fetching of bundle settings."""
        mock_ayon_api.get_addons_settings.return_value = sample_studio_settings

        result = get_bundle_settings("prod_bundle_v1", mock_console)

        assert result == sample_studio_settings
        mock_ayon_api.get_addons_settings.assert_called_once_with(
            bundle_name="prod_bundle_v1",
            project_name=None,
            variant="prod_bundle_v1",
        )

    @patch("gishant_scripts.ayon.analyze_bundles.ayon_api")
    def test_get_project_settings_success(self, mock_ayon_api, mock_console, sample_project_settings):
        """Test successful fetching of project settings."""
        mock_ayon_api.get_addons_settings.return_value = sample_project_settings

        result = get_project_settings("prod_bundle_v1", "test_project", mock_console)

        assert result == sample_project_settings
        mock_ayon_api.get_addons_settings.assert_called_once_with(
            bundle_name="prod_bundle_v1",
            project_name="test_project",
            variant="prod_bundle_v1",
        )

    @patch("gishant_scripts.ayon.analyze_bundles.ayon_api")
    def test_get_project_anatomy_success(self, mock_ayon_api, mock_console, sample_anatomy):
        """Test successful fetching of project anatomy."""
        # The implementation uses .get("anatomy", {}) so we need to return a dict
        mock_project_data = {"anatomy": sample_anatomy}
        mock_ayon_api.get_project.return_value = mock_project_data

        result = get_project_anatomy("test_project", mock_console)

        assert result == sample_anatomy
        mock_ayon_api.get_project.assert_called_once_with("test_project")

    @patch("gishant_scripts.ayon.analyze_bundles.ayon_api")
    def test_get_all_projects_success(self, mock_api, mock_console, sample_projects_data):
        """Test successful projects retrieval."""
        mock_api.get_projects.return_value = sample_projects_data

        result = get_all_projects(mock_console)

        assert result == sample_projects_data
        assert len(result) == 2


class TestCompareSettings:
    """Tests for settings comparison functionality."""

    def test_compare_basic_settings(
        self,
        sample_bundle_data,
        sample_bundle_data_2,
        sample_studio_settings,
        sample_studio_settings_2,
    ):
        """Test basic settings comparison."""
        result = compare_settings(
            sample_bundle_data,
            sample_studio_settings,
            sample_bundle_data_2,
            sample_studio_settings_2,
        )

        assert "metadata" in result
        assert "addons" in result
        assert "settings" in result
        assert result["metadata"]["bundle1"]["name"] == "test-bundle-1.0"
        assert result["metadata"]["bundle2"]["name"] == "test-bundle-2.0"

    def test_compare_with_project_settings(
        self,
        sample_bundle_data,
        sample_bundle_data_2,
        sample_studio_settings,
        sample_studio_settings_2,
        sample_project_settings,
    ):
        """Test comparison with project settings included."""
        result = compare_settings(
            sample_bundle_data,
            sample_studio_settings,
            sample_bundle_data_2,
            sample_studio_settings_2,
            bundle1_project_settings=sample_project_settings,
            bundle2_project_settings=sample_project_settings,
        )

        assert "project_settings" in result

    def test_compare_with_anatomy(
        self,
        sample_bundle_data,
        sample_bundle_data_2,
        sample_studio_settings,
        sample_studio_settings_2,
        sample_anatomy,
    ):
        """Test comparison with anatomy included."""
        result = compare_settings(
            sample_bundle_data,
            sample_studio_settings,
            sample_bundle_data_2,
            sample_studio_settings_2,
            anatomy1=sample_anatomy,
            anatomy2=sample_anatomy,
        )

        assert "anatomy" in result

    def test_compare_with_max_depth(
        self,
        sample_bundle_data,
        sample_bundle_data_2,
        sample_studio_settings,
        sample_studio_settings_2,
    ):
        """Test comparison with depth limit."""
        result = compare_settings(
            sample_bundle_data,
            sample_studio_settings,
            sample_bundle_data_2,
            sample_studio_settings_2,
            max_depth=2,
        )

        # Settings should be flattened with max depth
        assert result["settings"]["bundle1"]
        assert result["settings"]["bundle2"]


class TestGetDifferences:
    """Tests for difference extraction."""

    def test_get_differences_only_diff(self, sample_comparison_result):
        """Test getting only differences."""
        result = get_differences(sample_comparison_result, only_diff=True)

        assert "metadata" in result
        assert "addons" in result
        assert "settings" in result
        assert isinstance(result["metadata"], list)
        assert isinstance(result["addons"], list)

    def test_get_differences_all(self, sample_comparison_result):
        """Test getting all settings including unchanged."""
        result = get_differences(sample_comparison_result, only_diff=False)

        # Should include more items when not filtering
        assert len(result["addons"]) > 0

    def test_metadata_differences(self, sample_comparison_result):
        """Test metadata difference detection."""
        result = get_differences(sample_comparison_result, only_diff=True)

        # Should detect installer version change
        metadata_diffs = [d for d in result["metadata"] if d["key"] == "installerVersion"]
        assert len(metadata_diffs) == 1
        assert metadata_diffs[0]["bundle1"] == "1.0.0"
        assert metadata_diffs[0]["bundle2"] == "2.0.0"

    def test_addon_differences(self, sample_comparison_result):
        """Test addon version difference detection."""
        result = get_differences(sample_comparison_result, only_diff=True)

        addon_diffs = result["addons"]

        # Should detect maya version bump
        maya_diff = [d for d in addon_diffs if d["key"] == "maya"]
        assert len(maya_diff) == 1
        assert maya_diff[0]["bundle1"] == "1.0.0"
        assert maya_diff[0]["bundle2"] == "1.1.0"
        assert maya_diff[0]["status"] == "changed"

        # Should detect new unreal addon
        unreal_diff = [d for d in addon_diffs if d["key"] == "unreal"]
        assert len(unreal_diff) == 1
        assert unreal_diff[0]["bundle1"] is None
        assert unreal_diff[0]["bundle2"] == "1.0.0"
        assert unreal_diff[0]["status"] == "added"


class TestExportFunctions:
    """Tests for export functionality."""

    def test_export_to_json(self, sample_comparison_result, tmp_path):
        """Test JSON export."""
        output_file = tmp_path / "comparison.json"
        differences = get_differences(sample_comparison_result, only_diff=True)

        export_to_json(sample_comparison_result, differences, output_file)

        assert output_file.exists()

        # Verify JSON structure
        with open(output_file) as f:
            data = json.load(f)
            assert "comparison" in data
            assert "differences" in data

    def test_export_to_markdown(self, tmp_path):
        """Test Markdown export."""
        output_file = tmp_path / "comparison.md"
        differences = {
            "metadata": [{"key": "test", "bundle1": "v1", "bundle2": "v2", "status": "changed"}],
            "addons": [],
            "dependencies": [],
            "settings": [],
            "project_settings": [],
            "anatomy": [],
        }

        export_to_markdown(differences, "bundle1", "bundle2", output_file)

        assert output_file.exists()

        # Verify markdown content
        content = output_file.read_text()
        assert "# Bundle Comparison" in content
        assert "bundle1" in content
        assert "bundle2" in content

    def test_export_to_markdown_with_project(self, tmp_path):
        """Test Markdown export with project name."""
        output_file = tmp_path / "comparison.md"
        differences = {
            "metadata": [],
            "addons": [],
            "dependencies": [],
            "settings": [],
            "project_settings": [],
            "anatomy": [],
        }

        export_to_markdown(
            differences,
            "bundle1",
            "bundle2",
            output_file,
            project_name="test-project",
        )

        content = output_file.read_text()
        assert "test-project" in content


class TestInteractiveFunctions:
    """Tests for interactive selection functions."""

    @patch("gishant_scripts.ayon.analyze_bundles.Prompt.ask")
    def test_interactive_project_selection(self, mock_prompt, sample_projects_data, mock_console):
        """Test interactive project selection."""
        from gishant_scripts.ayon.analyze_bundles import interactive_project_selection

        mock_prompt.return_value = "1"

        result = interactive_project_selection(sample_projects_data, mock_console)

        assert result == "test_project_1"

    @patch("gishant_scripts.ayon.analyze_bundles.Prompt.ask")
    def test_interactive_bundle_selection(self, mock_prompt, sample_bundles_data, mock_console):
        """Test interactive bundle selection."""
        from gishant_scripts.ayon.analyze_bundles import interactive_bundle_selection

        # User selects bundles 1 and 2
        mock_prompt.side_effect = ["1", "2"]

        bundle1, bundle2 = interactive_bundle_selection(sample_bundles_data, mock_console)

        assert bundle1 == "test-bundle-1.0"
        assert bundle2 == "test-bundle-2.0"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_bundles_data(self):
        """Test handling of empty bundles data."""
        bundles_data = {"bundles": []}

        with pytest.raises(BundleNotFoundError):
            get_bundle_by_name(bundles_data, "any-bundle")

    def test_flatten_empty_dict(self):
        """Test flattening empty dictionary."""
        result = flatten_dict({})
        assert result == {}

    def test_comparison_with_missing_keys(self):
        """Test comparison with missing keys in bundles."""
        bundle1 = {"name": "b1", "addons": {}}
        bundle2 = {"name": "b2", "addons": {}}
        settings1 = {}
        settings2 = {}

        result = compare_settings(bundle1, settings1, bundle2, settings2)

        assert "metadata" in result
        assert "addons" in result

    def test_get_differences_empty_comparison(self):
        """Test getting differences from empty comparison."""
        comparison = {
            "metadata": {"bundle1": {}, "bundle2": {}},
            "addons": {"bundle1": {}, "bundle2": {}},
            "dependencies": {"bundle1": {}, "bundle2": {}},
            "settings": {"bundle1": {}, "bundle2": {}},
        }

        result = get_differences(comparison)

        assert all(len(items) == 0 for items in result.values())

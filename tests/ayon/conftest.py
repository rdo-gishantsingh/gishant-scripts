"""Test fixtures for AYON tools."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_console():
    """Mock Rich Console for testing."""
    # Don't use spec=Console because Rich internals access many dynamic attributes
    console = MagicMock()
    console.print = MagicMock()
    console.get_time = MagicMock(return_value=0.0)
    return console


@pytest.fixture
def sample_bundle_data():
    """Sample bundle data for testing."""
    return {
        "name": "test-bundle-1.0",
        "installerVersion": "1.0.0",
        "isProduction": True,
        "isStaging": False,
        "isDev": False,
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "addons": {
            "maya": "1.0.0",
            "nuke": "2.0.0",
            "core": "3.0.0",
        },
        "dependencyPackages": {
            "python": "3.11.0",
            "qt": "5.15.2",
        },
    }


@pytest.fixture
def sample_bundle_data_2():
    """Second sample bundle data for comparison testing."""
    return {
        "name": "test-bundle-2.0",
        "installerVersion": "2.0.0",
        "isProduction": False,
        "isStaging": True,
        "isDev": False,
        "createdAt": "2024-02-01T00:00:00Z",
        "updatedAt": "2024-02-02T00:00:00Z",
        "addons": {
            "maya": "1.1.0",  # Version bump
            "nuke": "2.0.0",  # Same version
            "unreal": "1.0.0",  # New addon
        },
        "dependencyPackages": {
            "python": "3.11.0",
            "qt": "6.0.0",  # Version bump
        },
    }


@pytest.fixture
def sample_studio_settings():
    """Sample studio settings for testing."""
    return {
        "applications": {
            "maya": {
                "enabled": True,
                "version": "2024",
            },
        },
        "deadline": {
            "enabled": True,
            "url": "http://deadline-server:8082",
        },
        "core": {
            "studio_name": "Test Studio",
            "studio_code": "TST",
        },
    }


@pytest.fixture
def sample_studio_settings_2():
    """Second sample studio settings for comparison."""
    return {
        "applications": {
            "maya": {
                "enabled": True,
                "version": "2025",  # Changed
            },
            "nuke": {  # New section
                "enabled": True,
                "version": "15.0",
            },
        },
        "deadline": {
            "enabled": False,  # Changed
            "url": "http://deadline-server:8082",
        },
        "core": {
            "studio_name": "Test Studio Updated",  # Changed
            "studio_code": "TST",
        },
    }


@pytest.fixture
def sample_project_settings():
    """Sample project-specific settings."""
    return {
        "maya": {
            "render_settings": {
                "arnold": {
                    "sampling": 5,
                    "threads": 8,
                },
            },
        },
        "deadline": {
            "pool": "renderPool",
            "group": "maya_renders",
        },
    }


@pytest.fixture
def sample_anatomy():
    """Sample project anatomy configuration."""
    return {
        "templates": {
            "work": "{root}/{project}/{asset}/work/{task}/{version}",
            "publish": "{root}/{project}/{asset}/publish/{subset}/{version}",
        },
        "roots": {
            "work": "/mnt/projects/work",
            "publish": "/mnt/projects/publish",
        },
        "attributes": {
            "fps": 25,
            "resolution_width": 1920,
            "resolution_height": 1080,
        },
    }


@pytest.fixture
def sample_bundles_data(sample_bundle_data, sample_bundle_data_2):
    """Sample bundles data structure from API."""
    return {
        "bundles": [sample_bundle_data, sample_bundle_data_2],
        "productionBundle": "test-bundle-1.0",
        "stagingBundle": "test-bundle-2.0",
        "devBundle": None,
    }


@pytest.fixture
def sample_projects_data():
    """Sample projects data from API."""
    return [
        {
            "name": "test_project_1",
            "code": "TP1",
            "library": False,
        },
        {
            "name": "test_project_2",
            "code": "TP2",
            "library": True,
        },
    ]


@pytest.fixture
def sample_comparison_result(
    sample_bundle_data,
    sample_bundle_data_2,
    sample_studio_settings,
    sample_studio_settings_2,
):
    """Sample comparison result from compare_settings."""
    return {
        "metadata": {
            "bundle1": {
                "name": sample_bundle_data["name"],
                "installerVersion": sample_bundle_data["installerVersion"],
                "isProduction": sample_bundle_data["isProduction"],
                "isStaging": sample_bundle_data["isStaging"],
                "isDev": sample_bundle_data["isDev"],
                "createdAt": sample_bundle_data["createdAt"],
                "updatedAt": sample_bundle_data["updatedAt"],
            },
            "bundle2": {
                "name": sample_bundle_data_2["name"],
                "installerVersion": sample_bundle_data_2["installerVersion"],
                "isProduction": sample_bundle_data_2["isProduction"],
                "isStaging": sample_bundle_data_2["isStaging"],
                "isDev": sample_bundle_data_2["isDev"],
                "createdAt": sample_bundle_data_2["createdAt"],
                "updatedAt": sample_bundle_data_2["updatedAt"],
            },
        },
        "addons": {
            "bundle1": sample_bundle_data["addons"],
            "bundle2": sample_bundle_data_2["addons"],
        },
        "dependencies": {
            "bundle1": sample_bundle_data["dependencyPackages"],
            "bundle2": sample_bundle_data_2["dependencyPackages"],
        },
        "settings": {
            "bundle1": sample_studio_settings,
            "bundle2": sample_studio_settings_2,
        },
    }


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Temporary directory for backup files."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@pytest.fixture
def mock_ayon_api():
    """Mock ayon_api module at the point of import."""
    with patch("gishant_scripts.ayon.analyze_bundles.ayon_api") as mock_api:
        mock_api.is_service_user.return_value = False
        mock_api.get_server_url.return_value = "http://test-server:5000"
        mock_api.get_rest_url.return_value = "http://test-server:5000/api"
        yield mock_api


@pytest.fixture
def mock_rdo_ayon_utils():
    """Mock rdo_ayon_utils module at the point of import."""
    with patch("gishant_scripts.ayon.analyze_bundles.ayon_utils") as mock_utils:
        mock_utils.set_connection.return_value = None
        mock_utils.get_server_url.return_value = "http://test-server:5000"
        mock_utils.get_api_key.return_value = "test-api-key"
        yield mock_utils

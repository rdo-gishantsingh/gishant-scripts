"""Unit tests for AYON settings diff utilities."""

from __future__ import annotations

import pytest

from gishant_scripts.ayon.diff import compare_settings, flatten_dict, get_differences


class TestFlattenDict:
    """Tests for flatten_dict()."""

    def test_empty_dict(self) -> None:
        assert flatten_dict({}) == {}

    def test_flat_dict_unchanged(self) -> None:
        data = {"a": 1, "b": "hello", "c": True}
        assert flatten_dict(data) == {"a": 1, "b": "hello", "c": True}

    def test_nested_one_level(self) -> None:
        data = {"outer": {"inner": "value"}}
        assert flatten_dict(data) == {"outer.inner": "value"}

    def test_nested_multiple_levels(self) -> None:
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert flatten_dict(data) == {"a.b.c.d": 42}

    def test_mixed_nested_and_flat(self) -> None:
        data = {"x": 1, "y": {"z": 2}, "w": "three"}
        result = flatten_dict(data)
        assert result == {"x": 1, "y.z": 2, "w": "three"}

    def test_empty_nested_dict_preserved(self) -> None:
        data = {"a": {}, "b": 1}
        result = flatten_dict(data)
        assert result == {"a": {}, "b": 1}

    def test_list_values_preserved(self) -> None:
        data = {"a": [1, 2, 3], "b": {"c": [4, 5]}}
        result = flatten_dict(data)
        assert result == {"a": [1, 2, 3], "b.c": [4, 5]}

    def test_custom_separator(self) -> None:
        data = {"a": {"b": "val"}}
        result = flatten_dict(data, sep="/")
        assert result == {"a/b": "val"}

    def test_parent_key(self) -> None:
        data = {"b": "val"}
        result = flatten_dict(data, parent_key="a")
        assert result == {"a.b": "val"}

    def test_max_depth_zero(self) -> None:
        """max_depth=0 should not recurse into nested dicts."""
        data = {"a": {"b": {"c": 1}}}
        result = flatten_dict(data, max_depth=0)
        assert result == {"a": {"b": {"c": 1}}}

    def test_max_depth_one(self) -> None:
        data = {"a": {"b": {"c": 1}}, "x": 2}
        result = flatten_dict(data, max_depth=1)
        assert result == {"a.b": {"c": 1}, "x": 2}

    def test_max_depth_unlimited(self) -> None:
        data = {"a": {"b": {"c": {"d": 1}}}}
        result = flatten_dict(data, max_depth=None)
        assert result == {"a.b.c.d": 1}


class TestCompareSettings:
    """Tests for compare_settings()."""

    @pytest.fixture()
    def bundle1_data(self) -> dict:
        return {
            "name": "prod_v1",
            "installerVersion": "1.0.0",
            "isProduction": True,
            "isStaging": False,
            "isDev": False,
            "createdAt": "2025-01-01",
            "updatedAt": "2025-01-02",
            "addons": {"maya": "0.5.0", "unreal": "0.3.0"},
            "dependencyPackages": {"linux": "dep_v1", "windows": "dep_v2"},
        }

    @pytest.fixture()
    def bundle2_data(self) -> dict:
        return {
            "name": "prod_v2",
            "installerVersion": "1.1.0",
            "isProduction": False,
            "isStaging": True,
            "isDev": False,
            "createdAt": "2025-02-01",
            "updatedAt": "2025-02-02",
            "addons": {"maya": "0.6.0", "nuke": "0.1.0"},
            "dependencyPackages": {"linux": "dep_v3"},
        }

    def test_metadata_populated(self, bundle1_data: dict, bundle2_data: dict) -> None:
        result = compare_settings(bundle1_data, {}, bundle2_data, {})
        assert result["metadata"]["bundle1"]["name"] == "prod_v1"
        assert result["metadata"]["bundle2"]["name"] == "prod_v2"

    def test_addons_populated(self, bundle1_data: dict, bundle2_data: dict) -> None:
        result = compare_settings(bundle1_data, {}, bundle2_data, {})
        assert result["addons"]["bundle1"] == {"maya": "0.5.0", "unreal": "0.3.0"}
        assert result["addons"]["bundle2"] == {"maya": "0.6.0", "nuke": "0.1.0"}

    def test_dependencies_populated(self, bundle1_data: dict, bundle2_data: dict) -> None:
        result = compare_settings(bundle1_data, {}, bundle2_data, {})
        assert result["dependencies"]["bundle1"] == {"linux": "dep_v1", "windows": "dep_v2"}
        assert result["dependencies"]["bundle2"] == {"linux": "dep_v3"}

    def test_settings_flattened(self, bundle1_data: dict, bundle2_data: dict) -> None:
        s1 = {"maya": {"render": {"quality": "high"}}}
        s2 = {"maya": {"render": {"quality": "low"}}}
        result = compare_settings(bundle1_data, s1, bundle2_data, s2)
        assert result["settings"]["bundle1"] == {"maya.render.quality": "high"}
        assert result["settings"]["bundle2"] == {"maya.render.quality": "low"}

    def test_project_settings_included_when_provided(self, bundle1_data: dict, bundle2_data: dict) -> None:
        ps1 = {"core": {"enabled": True}}
        ps2 = {"core": {"enabled": False}}
        result = compare_settings(bundle1_data, {}, bundle2_data, {}, ps1, ps2)
        assert "project_settings" in result
        assert result["project_settings"]["bundle1"] == {"core.enabled": True}

    def test_project_settings_excluded_when_none(self, bundle1_data: dict, bundle2_data: dict) -> None:
        result = compare_settings(bundle1_data, {}, bundle2_data, {})
        assert "project_settings" not in result

    def test_anatomy_included_when_provided(self, bundle1_data: dict, bundle2_data: dict) -> None:
        a1 = {"roots": {"work": "/projects"}}
        a2 = {"roots": {"work": "/other"}}
        result = compare_settings(bundle1_data, {}, bundle2_data, {}, anatomy1=a1, anatomy2=a2)
        assert "anatomy" in result

    def test_anatomy_excluded_when_none(self, bundle1_data: dict, bundle2_data: dict) -> None:
        result = compare_settings(bundle1_data, {}, bundle2_data, {})
        assert "anatomy" not in result


class TestGetDifferences:
    """Tests for get_differences()."""

    def _make_comparison(
        self,
        *,
        b1_addons: dict | None = None,
        b2_addons: dict | None = None,
        b1_settings: dict | None = None,
        b2_settings: dict | None = None,
    ) -> dict:
        """Build a minimal comparison dict for testing."""
        return {
            "metadata": {
                "bundle1": {"name": "b1", "version": "1.0"},
                "bundle2": {"name": "b2", "version": "1.0"},
            },
            "addons": {
                "bundle1": b1_addons or {},
                "bundle2": b2_addons or {},
            },
            "dependencies": {
                "bundle1": {},
                "bundle2": {},
            },
            "settings": {
                "bundle1": b1_settings or {},
                "bundle2": b2_settings or {},
            },
        }

    def test_identical_metadata_unchanged(self) -> None:
        comp = self._make_comparison()
        diffs = get_differences(comp)
        for entry in diffs["metadata"]:
            if entry["key"] == "version":
                assert entry["status"] == "unchanged"

    def test_different_metadata_marked_changed(self) -> None:
        comp = self._make_comparison()
        diffs = get_differences(comp)
        name_entry = next(e for e in diffs["metadata"] if e["key"] == "name")
        assert name_entry["status"] == "changed"
        assert name_entry["bundle1"] == "b1"
        assert name_entry["bundle2"] == "b2"

    def test_only_diff_filters_unchanged(self) -> None:
        comp = self._make_comparison()
        diffs = get_differences(comp, only_diff=True)
        for entry in diffs["metadata"]:
            assert entry["status"] != "unchanged"

    def test_addon_added(self) -> None:
        comp = self._make_comparison(b1_addons={}, b2_addons={"nuke": "0.1.0"})
        diffs = get_differences(comp)
        nuke = next(e for e in diffs["addons"] if e["key"] == "nuke")
        assert nuke["status"] == "added"
        assert nuke["bundle1"] is None
        assert nuke["bundle2"] == "0.1.0"

    def test_addon_removed(self) -> None:
        comp = self._make_comparison(b1_addons={"maya": "0.5.0"}, b2_addons={})
        diffs = get_differences(comp)
        maya = next(e for e in diffs["addons"] if e["key"] == "maya")
        assert maya["status"] == "removed"
        assert maya["bundle2"] is None

    def test_addon_changed(self) -> None:
        comp = self._make_comparison(b1_addons={"maya": "0.5.0"}, b2_addons={"maya": "0.6.0"})
        diffs = get_differences(comp)
        maya = next(e for e in diffs["addons"] if e["key"] == "maya")
        assert maya["status"] == "changed"

    def test_addon_unchanged(self) -> None:
        comp = self._make_comparison(b1_addons={"maya": "0.5.0"}, b2_addons={"maya": "0.5.0"})
        diffs = get_differences(comp)
        maya = next(e for e in diffs["addons"] if e["key"] == "maya")
        assert maya["status"] == "unchanged"

    def test_settings_added(self) -> None:
        comp = self._make_comparison(b1_settings={}, b2_settings={"maya.quality": "high"})
        diffs = get_differences(comp)
        entry = next(e for e in diffs["settings"] if e["key"] == "maya.quality")
        assert entry["status"] == "added"

    def test_settings_removed(self) -> None:
        comp = self._make_comparison(b1_settings={"maya.quality": "high"}, b2_settings={})
        diffs = get_differences(comp)
        entry = next(e for e in diffs["settings"] if e["key"] == "maya.quality")
        assert entry["status"] == "removed"

    def test_addon_filter(self) -> None:
        comp = self._make_comparison(
            b1_addons={"maya": "0.5.0", "nuke": "0.1.0"},
            b2_addons={"maya": "0.6.0", "nuke": "0.2.0"},
            b1_settings={"maya.quality": "high", "nuke.threads": 4},
            b2_settings={"maya.quality": "low", "nuke.threads": 8},
        )
        diffs = get_differences(comp, addon_filter=["maya"])
        addon_keys = {e["key"] for e in diffs["addons"]}
        assert "maya" in addon_keys
        assert "nuke" not in addon_keys
        settings_keys = {e["key"] for e in diffs["settings"]}
        assert "maya.quality" in settings_keys
        assert "nuke.threads" not in settings_keys

    def test_project_settings_differences(self) -> None:
        comp = self._make_comparison()
        comp["project_settings"] = {
            "bundle1": {"core.enabled": True},
            "bundle2": {"core.enabled": False},
        }
        diffs = get_differences(comp)
        entry = next(e for e in diffs["project_settings"] if e["key"] == "core.enabled")
        assert entry["status"] == "changed"

    def test_anatomy_differences(self) -> None:
        comp = self._make_comparison()
        comp["anatomy"] = {
            "bundle1": {"roots.work": "/projects"},
            "bundle2": {"roots.work": "/other"},
        }
        diffs = get_differences(comp)
        entry = next(e for e in diffs["anatomy"] if e["key"] == "roots.work")
        assert entry["status"] == "changed"

    def test_empty_comparison(self) -> None:
        comp = self._make_comparison()
        diffs = get_differences(comp)
        assert diffs["addons"] == []
        assert diffs["dependencies"] == []
        assert diffs["settings"] == []

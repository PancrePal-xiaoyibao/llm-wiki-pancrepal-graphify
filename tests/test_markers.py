"""Tests for xyb.markers — biomarker configuration system."""

import tempfile
from pathlib import Path

import pytest

from xyb.markers import (
    MARKER_CATEGORIES,
    get_all_markers,
    get_categories,
    get_default_markers,
    get_markers_for_category,
    is_abnormal,
    load_marker_config,
)


# ---------------------------------------------------------------------------
# Default markers
# ---------------------------------------------------------------------------

class TestDefaultMarkers:
    def test_default_marker_count(self):
        defaults = get_default_markers()
        assert len(defaults) == 5

    def test_default_marker_names(self):
        defaults = get_default_markers()
        assert "CA19-9" in defaults
        assert "CEA" in defaults
        assert "CA125" in defaults
        assert "CA724" in defaults
        assert "CA50" in defaults


# ---------------------------------------------------------------------------
# All markers
# ---------------------------------------------------------------------------

class TestAllMarkers:
    def test_at_least_30_markers(self):
        all_m = get_all_markers()
        assert len(all_m) >= 30, f"Expected >=30 markers, got {len(all_m)}"

    def test_each_marker_has_unit(self):
        for name, info in get_all_markers().items():
            assert "unit" in info, f"{name} missing unit"
            assert isinstance(info["unit"], str)

    def test_each_marker_has_thresholds(self):
        for name, info in get_all_markers().items():
            has_high = info.get("ref_high") is not None
            has_low = info.get("ref_low") is not None
            assert has_high or has_low, f"{name} has neither ref_high nor ref_low"


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class TestCategories:
    def test_all_categories_present(self):
        cats = get_categories()
        for expected in [
            "tumor", "tumor_extended", "infection", "glucose",
            "liver_kidney", "blood_routine", "coagulation", "nutrition",
        ]:
            assert expected in cats

    def test_default_only(self):
        defaults = get_categories(default_only=True)
        assert defaults == ["tumor"]

    def test_get_markers_for_category(self):
        markers = get_markers_for_category("tumor")
        assert "CA19-9" in markers
        assert len(markers) == 5

    def test_get_markers_for_bad_category(self):
        with pytest.raises(KeyError):
            get_markers_for_category("nonexistent")


# ---------------------------------------------------------------------------
# is_abnormal
# ---------------------------------------------------------------------------

class TestIsAbnormal:
    def test_normal_ca199(self):
        assert is_abnormal("CA19-9", 20.0) is False

    def test_high_ca199(self):
        assert is_abnormal("CA19-9", 50.0) is True

    def test_boundary_ca199(self):
        assert is_abnormal("CA19-9", 37.0) is False  # exactly at ref_high

    def test_low_alb(self):
        # ALB has ref_low=35, no ref_high
        assert is_abnormal("ALB", 30.0) is True

    def test_normal_alb(self):
        assert is_abnormal("ALB", 40.0) is False

    def test_egfr_low(self):
        assert is_abnormal("eGFR", 80.0) is True

    def test_egfr_normal(self):
        assert is_abnormal("eGFR", 100.0) is False

    def test_unknown_marker_raises(self):
        with pytest.raises(KeyError):
            is_abnormal("FAKE_MARKER", 1.0)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestLoadMarkerConfig:
    def test_no_config_returns_defaults(self):
        # When no config file exists, returns defaults
        result = load_marker_config(config_path="/nonexistent/path/xyb.toml")
        defaults = get_all_markers()
        assert result == defaults

    def test_load_toml_overrides(self):
        toml_content = """
[markers.CA19-9]
ref_high = 30.0

[markers.CUSTOM_MARKER]
unit = "ng/mL"
ref_high = 100.0
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as f:
            f.write(toml_content)
            f.flush()
            result = load_marker_config(f.name)

        assert result["CA19-9"]["ref_high"] == 30.0  # overridden
        assert result["CA19-9"]["unit"] == "U/mL"  # preserved
        assert result["CEA"]["ref_high"] == 5.0  # unchanged
        assert "CUSTOM_MARKER" in result

    def teardown_method(self):
        # clean up temp files if any were left
        pass

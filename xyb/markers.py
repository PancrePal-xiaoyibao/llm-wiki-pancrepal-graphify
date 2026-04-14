"""
Biomarker configuration system for 小医宝 (XiaoYiBao).

Provides 30+ clinical biomarker indicators organized by category,
with reference ranges, abnormality detection, and TOML config loading.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Marker category definitions
# ---------------------------------------------------------------------------
# Each marker entry: {"unit": str, "ref_high": float, "ref_low": float?}

MARKER_CATEGORIES: dict[str, dict[str, Any]] = {
    "tumor": {
        "default": True,
        "markers": {
            "CA19-9": {"unit": "U/mL", "ref_high": 37.0},
            "CEA": {"unit": "ng/mL", "ref_high": 5.0},
            "CA125": {"unit": "U/mL", "ref_high": 35.0},
            "CA724": {"unit": "U/mL", "ref_high": 6.9},
            "CA50": {"unit": "U/mL", "ref_high": 25.0},
        },
    },
    "tumor_extended": {
        "default": False,
        "markers": {
            "AFP": {"unit": "ng/mL", "ref_high": 7.0},
            "CA15-3": {"unit": "U/mL", "ref_high": 25.0},
            "CA242": {"unit": "U/mL", "ref_high": 20.0},
            "SCC": {"unit": "ng/mL", "ref_high": 1.5},
            "NSE": {"unit": "ng/mL", "ref_high": 16.3},
            "CYFRA21-1": {"unit": "ng/mL", "ref_high": 3.3},
        },
    },
    "infection": {
        "default": False,
        "markers": {
            "CRP": {"unit": "mg/L", "ref_high": 10.0},
            "PCT": {"unit": "ng/mL", "ref_high": 0.5},
            "IL-6": {"unit": "pg/mL", "ref_high": 7.0},
            "WBC": {"unit": "×10⁹/L", "ref_high": 10.0},
        },
    },
    "glucose": {
        "default": False,
        "markers": {
            "空腹血糖": {"unit": "mmol/L", "ref_high": 6.1},
            "餐后血糖": {"unit": "mmol/L", "ref_high": 7.8},
            "HbA1c": {"unit": "%", "ref_high": 6.5},
            "胰岛素": {"unit": "μU/mL", "ref_high": 25.0},
            "C肽": {"unit": "ng/mL", "ref_high": 4.0},
        },
    },
    "liver_kidney": {
        "default": False,
        "markers": {
            "ALT": {"unit": "U/L", "ref_high": 40.0},
            "AST": {"unit": "U/L", "ref_high": 40.0},
            "TBIL": {"unit": "μmol/L", "ref_high": 26.0},
            "DBIL": {"unit": "μmol/L", "ref_high": 6.8},
            "ALB": {"unit": "g/L", "ref_high": None, "ref_low": 35.0},
            "Cr": {"unit": "μmol/L", "ref_high": 104.0},
            "BUN": {"unit": "mmol/L", "ref_high": 7.1},
            "eGFR": {"unit": "mL/min", "ref_high": None, "ref_low": 90.0},
        },
    },
    "blood_routine": {
        "default": False,
        "markers": {
            "ANC": {"unit": "×10⁹/L", "ref_high": None, "ref_low": 2.0},
            "PLT": {"unit": "×10⁹/L", "ref_high": None, "ref_low": 100.0},
            "HGB": {"unit": "g/L", "ref_high": None, "ref_low": 110.0},
        },
    },
    "coagulation": {
        "default": False,
        "markers": {
            "D-dimer": {"unit": "μg/mL", "ref_high": 0.5},
            "FIB": {"unit": "g/L", "ref_high": 4.0},
            "PT": {"unit": "s", "ref_high": 13.0},
        },
    },
    "nutrition": {
        "default": False,
        "markers": {
            "前白蛋白": {"unit": "mg/L", "ref_high": None, "ref_low": 200.0},
            "转铁蛋白": {"unit": "g/L", "ref_high": None, "ref_low": 2.0},
            "总蛋白": {"unit": "g/L", "ref_high": None, "ref_low": 65.0},
            "K": {"unit": "mmol/L", "ref_high": None, "ref_low": 3.5},
            "Na": {"unit": "mmol/L", "ref_high": None, "ref_low": 136.0},
            "Ca": {"unit": "mmol/L", "ref_high": None, "ref_low": 2.1},
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_default_markers() -> list[str]:
    """Return the 5 core default tumor markers (always enabled)."""
    return list(MARKER_CATEGORIES["tumor"]["markers"].keys())


def get_all_markers() -> dict[str, dict[str, Any]]:
    """Return a flat dict of all markers: {name: {unit, ref_high, ref_low}}."""
    result: dict[str, dict[str, Any]] = {}
    for cat in MARKER_CATEGORIES.values():
        for name, info in cat["markers"].items():
            result[name] = {
                "unit": info["unit"],
                "ref_high": info.get("ref_high"),
                "ref_low": info.get("ref_low"),
            }
    return result


def get_categories(default_only: bool = False) -> list[str]:
    """Return list of category names. If default_only, only those with default=True."""
    if default_only:
        return [k for k, v in MARKER_CATEGORIES.items() if v.get("default")]
    return list(MARKER_CATEGORIES.keys())


def get_markers_for_category(category: str) -> dict[str, dict[str, Any]]:
    """Return markers dict for a single category."""
    if category not in MARKER_CATEGORIES:
        raise KeyError(f"Unknown marker category: {category!r}")
    return dict(MARKER_CATEGORIES[category]["markers"])


def is_abnormal(marker_name: str, value: float) -> bool:
    """Check whether a marker value is outside its reference range.

    - If marker has ref_high only: abnormal when value > ref_high
    - If marker has ref_low only: abnormal when value < ref_low
    - If marker has both: abnormal when value > ref_high OR value < ref_low
    """
    all_markers = get_all_markers()
    if marker_name not in all_markers:
        raise KeyError(f"Unknown marker: {marker_name!r}")

    info = all_markers[marker_name]
    ref_high = info.get("ref_high")
    ref_low = info.get("ref_low")

    if ref_high is not None and value > ref_high:
        return True
    if ref_low is not None and value < ref_low:
        return True
    return False


def load_marker_config(config_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load marker overrides from a TOML config file and merge with defaults.

    Looks for a ``[markers]`` section in the TOML file. Each key should be a
    marker name whose value is a dict with optional ``unit``, ``ref_high``,
    ``ref_low`` keys.

    If *config_path* is ``None``, looks for ``xyb.toml`` in the current
    working directory and its parents.
    """
    # Lazy import so toml is only required when this function is called
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            raise ImportError(
                "tomllib (Python 3.11+) or tomli package is required to parse TOML configs"
            )

    if config_path is None:
        config_path = _find_config_file()
    else:
        config_path = Path(config_path)

    if config_path is None or not config_path.exists():
        return get_all_markers()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    overrides: dict[str, dict[str, Any]] = raw.get("markers", {})

    # Merge: start from defaults, apply overrides
    merged = get_all_markers()
    for name, info in overrides.items():
        if name in merged:
            merged[name].update(info)
        else:
            merged[name] = info

    return merged


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_config_file(
    filename: str = "xyb.toml",
    start: Path | None = None,
) -> Path | None:
    """Walk up from *start* looking for *filename*."""
    current = start or Path.cwd()
    while True:
        candidate = current / filename
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent

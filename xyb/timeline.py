"""Timeline utilities for medical document date extraction and ordering."""
from __future__ import annotations
import re
from pathlib import Path


# Date patterns ordered by specificity
_DATE_PATTERNS = [
    # ISO: 2024-03-15, 2024/03/15
    (re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'), '{y}-{m:02d}-{d:02d}'),
    # Compact: 20240315
    (re.compile(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)'), '{y}-{m:02d}-{d:02d}'),
    # Chinese: 2024年3月15日
    (re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'), '{y}-{m:02d}-{d:02d}'),
    # Year-month only: 2024-03 or 202403
    (re.compile(r'(\d{4})[-/](0[1-9]|1[0-2])(?:\D|$)'), '{y}-{m:02d}'),
    (re.compile(r'(20\d{2})(0[1-9]|1[0-2])(?!\d)'), '{y}-{m:02d}'),
]

_DIR_DATE_PATTERNS = [
    # Dir with date prefix: 2024-03-15_xxx or 20240315_xxx
    (re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'), '{y}-{m:02d}-{d:02d}'),
    (re.compile(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)'), '{y}-{m:02d}-{d:02d}'),
    (re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'), '{y}-{m:02d}-{d:02d}'),
    # Year-month in dir
    (re.compile(r'(\d{4})[-/](0[1-9]|1[0-2])'), '{y}-{m:02d}'),
]


def extract_date_from_filename(path: str | Path) -> str | None:
    """Parse date from a filename like 2024-03-15_report.pdf, 20240315.pdf, 2024年3月15日.txt."""
    name = Path(path).stem
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(name)
        if m:
            groups = m.groups()
            y = int(groups[0])
            month = int(groups[1])
            if len(groups) >= 3:
                d = int(groups[2])
                return fmt.format(y=y, m=month, d=d)
            return fmt.format(y=y, m=month)
    return None


def extract_date_from_dirname(path: str | Path) -> str | None:
    """Parse date from a directory name like '2024-03_第一次化疗' or '2024-03-15_followup'."""
    name = Path(path).name
    for pattern, fmt in _DIR_DATE_PATTERNS:
        m = pattern.search(name)
        if m:
            groups = m.groups()
            y = int(groups[0])
            month = int(groups[1])
            if len(groups) >= 3:
                d = int(groups[2])
                return fmt.format(y=y, m=month, d=d)
            return fmt.format(y=y, m=month)
    return None


def build_timeline(files_with_dates: list[tuple[Path, str | None]]) -> list[dict]:
    """Sort files by date and group into timeline entries.

    Args:
        files_with_dates: list of (file_path, date_string_or_None)

    Returns:
        Sorted list of {date, files, description} dicts, grouped by date.
    """
    # Filter out files without dates
    dated = [(f, d) for f, d in files_with_dates if d]

    # Sort by date string (ISO format sorts lexicographically)
    dated.sort(key=lambda x: x[1])

    # Group by date
    groups: dict[str, list[Path]] = {}
    for f, d in dated:
        groups.setdefault(d, []).append(f)

    result = []
    for date_str in sorted(groups.keys()):
        files = groups[date_str]
        filenames = [f.name for f in files]
        if len(files) == 1:
            desc = filenames[0]
        else:
            desc = f"{len(files)} 份文档: {', '.join(filenames[:3])}"
            if len(filenames) > 3:
                desc += f" 等{len(filenames)}个"

        result.append({
            "date": date_str,
            "files": [str(f) for f in files],
            "description": desc,
        })

    return result


def merge_timeline_events(events: list[dict]) -> list[dict]:
    """Deduplicate timeline events by (date, description).

    Later events with the same (date, description) are merged: their
    related_nodes are combined. Preserves insertion order (by date).
    """
    seen: dict[tuple[str, str], dict] = {}
    for ev in events:
        date = ev.get("date", "")
        desc = ev.get("description", "")
        key = (date, desc)
        if key in seen:
            existing = seen[key]
            existing_nodes = set(existing.get("related_nodes", []))
            new_nodes = set(ev.get("related_nodes", []))
            existing["related_nodes"] = list(existing_nodes | new_nodes)
        else:
            seen[key] = {
                "date": date,
                "description": desc,
                "related_nodes": list(ev.get("related_nodes", [])),
            }
    return list(seen.values())

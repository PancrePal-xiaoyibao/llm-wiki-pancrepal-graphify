"""Unified medical document extraction dispatcher.

Routes files to the appropriate extractor based on file type,
then optionally runs LLM-based entity extraction on raw text.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from .detect import FileType


def _make_id(*parts: str) -> str:
    """Build a stable node ID from one or more name parts."""
    import re
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", combined)
    return cleaned.strip("_").lower()[:80]


def extract(path: Path, file_type: FileType, llm_client: Any = None) -> dict:
    """Extract medical entities from a file based on its type.

    Returns dict with keys: nodes, edges, timeline_events, source_file.
    """
    path = Path(path)

    if file_type == FileType.DICOM:
        return _extract_dicom(path)
    elif file_type == FileType.PDF:
        return _extract_pdf(path, llm_client)
    elif file_type == FileType.IMAGE:
        return _extract_image(path, llm_client)
    elif file_type == FileType.OFFICE:
        return _extract_office(path, llm_client)
    elif file_type == FileType.DOCUMENT:
        return _extract_document(path, llm_client)
    else:
        return _empty_result(str(path))


def _extract_dicom(path: Path) -> dict:
    """Extract DICOM metadata."""
    try:
        from .extract_dicom import extract_dicom
        return extract_dicom(path)
    except ImportError:
        return _empty_result(str(path), error="pydicom not installed")


def _extract_pdf(path: Path, llm_client: Any) -> dict:
    """Extract PDF text, then optionally run LLM extraction."""
    try:
        from .extract_pdf import extract_pdf
        raw = extract_pdf(path)
    except ImportError:
        return _empty_result(str(path), error="pypdf not installed")

    text = raw.get("text", "")
    if not text.strip():
        return _empty_result(str(path))

    if llm_client:
        return _llm_extract_text(text, str(path), llm_client)

    # No LLM — return raw text as a document node
    return {
        "nodes": [{
            "id": f"doc_{path.stem}",
            "node_type": "Examination",
            "label": path.name,
            "source_file": str(path),
            "properties": {"text_preview": text[:500], "page_count": raw.get("page_count", 0)},
        }],
        "edges": [],
        "timeline_events": [],
        "source_file": str(path),
    }


def _extract_image(path: Path, llm_client: Any) -> dict:
    """Extract medical info from image via Vision model."""
    if llm_client:
        from .extract_medical import extract_from_image
        return extract_from_image(path, llm_client)

    return _empty_result(str(path))


def _extract_office(path: Path, llm_client: Any) -> dict:
    """Extract docx/xlsx content."""
    suffix = path.suffix.lower()

    if suffix == ".docx":
        try:
            from .extract_office import extract_docx
            raw = extract_docx(path)
        except ImportError:
            return _empty_result(str(path), error="python-docx not installed")
        text = raw.get("text", "")
        if llm_client and text.strip():
            return _llm_extract_text(text, str(path), llm_client)
        return _empty_result(str(path))

    elif suffix == ".xlsx":
        try:
            from .extract_office import extract_xlsx
            raw = extract_xlsx(path)
        except ImportError:
            return _empty_result(str(path), error="openpyxl not installed")

        # Try structured biomarker extraction
        from .extract_medical import extract_xlsx_structured
        sheets = raw.get("sheets", [])
        if sheets:
            return extract_xlsx_structured(sheets, str(path))
        return _empty_result(str(path))

    return _empty_result(str(path))


def _extract_document(path: Path, llm_client: Any) -> dict:
    """Extract text from .md/.txt files."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return _empty_result(str(path))

    if not text.strip():
        return _empty_result(str(path))

    if llm_client:
        return _llm_extract_text(text, str(path), llm_client)

    return {
        "nodes": [{
            "id": f"doc_{path.stem}",
            "node_type": "Examination",
            "label": path.name,
            "source_file": str(path),
            "properties": {"text_preview": text[:500]},
        }],
        "edges": [],
        "timeline_events": [],
        "source_file": str(path),
    }


def _llm_extract_text(text: str, source_file: str, llm_client: Any) -> dict:
    """Run LLM-based entity extraction on text."""
    try:
        from .extract_medical import extract_from_text
        return extract_from_text(text, source_file, llm_client)
    except Exception as e:
        return _empty_result(source_file, error=str(e))


def _empty_result(source_file: str, error: str | None = None) -> dict:
    """Return empty extraction result."""
    result = {
        "nodes": [],
        "edges": [],
        "timeline_events": [],
        "source_file": source_file,
    }
    if error:
        result["error"] = error
    return result

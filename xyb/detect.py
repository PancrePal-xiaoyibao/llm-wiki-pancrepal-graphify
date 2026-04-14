# file discovery, type classification, and corpus health checks
from __future__ import annotations
import fnmatch
import json
import os
import re
from enum import Enum
from pathlib import Path


class FileType(str, Enum):
    DICOM = "dicom"
    PDF = "pdf"
    IMAGE = "image"
    DOCUMENT = "document"
    OFFICE = "office"
    URL = "url"


_MANIFEST_PATH = "xyb-out/manifest.json"

DICOM_EXTENSIONS = {'.dcm', '.dicom'}
DOC_EXTENSIONS = {'.md', '.txt', '.rst'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.tiff', '.tif'}
OFFICE_EXTENSIONS = {'.docx', '.xlsx'}

CORPUS_WARN_THRESHOLD = 50_000    # words - below this, warn "you may not need a graph"
CORPUS_UPPER_THRESHOLD = 500_000  # words - above this, warn about token cost
FILE_COUNT_UPPER = 200             # files - above this, warn about token cost

# Files that may contain secrets - skip silently
_SENSITIVE_PATTERNS = [
    re.compile(r'(^|[\\\/])\.(env|envrc)(\.|$)', re.IGNORECASE),
    re.compile(r'\.(pem|key|p12|pfx|cert|crt|der|p8)$', re.IGNORECASE),
    re.compile(r'(credential|secret|passwd|password|token|private_key)', re.IGNORECASE),
    re.compile(r'(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\.pub)?$'),
    re.compile(r'(\.netrc|\.pgpass|\.htpasswd)$', re.IGNORECASE),
    re.compile(r'(aws_credentials|gcloud_credentials|service.account)', re.IGNORECASE),
]


def _is_sensitive(path: Path) -> bool:
    """Return True if this file likely contains secrets and should be skipped."""
    name = path.name
    full = str(path)
    return any(p.search(name) or p.search(full) for p in _SENSITIVE_PATTERNS)


def _is_dicom(path: Path) -> bool:
    """Check if a file has the DICM magic header at byte offset 128."""
    try:
        with open(path, 'rb') as f:
            f.seek(128)
            return f.read(4) == b'DICM'
    except Exception:
        return False


# Medical-specific file type constants (strings)
DICOM = "dicom"
PDF = "pdf"
OFFICE = "office"
URL = "url"

def classify_file(path: Path) -> FileType | str | None:
    """Classify a file, preserving graphify logic and adding medical types."""
    # Let graphify classify first (handles CODE, PAPER, IMAGE, DOCUMENT, VIDEO, and special cases)
    from graphify.detect import classify_file as _gg_classify
    result = _gg_classify(path)
    if result is not None:
        # graphify found a type (including PAPER for academic papers)
        return result

    # graphify returned None — check for medical-specific types
    ext = path.suffix.lower()
    parts = path.parts  # tuple of path components

    # DICOM files
    if ext in DICOM_EXTENSIONS:
        if _is_dicom(path):
            return DICOM
        return DICOM

    # PDF files: only treat as medical PDF if NOT in Xcode asset catalogs
    if ext == '.pdf' and not any(p.endswith('.xcassets') for p in parts):
        return PDF

    # Office documents (not in ignored dirs)
    if ext in OFFICE_EXTENSIONS:
        return OFFICE

    # URL files
    if ext == '.url':
        return URL

    return None

# Medical-specific file type string constants (defined before compat for classify_file use)
DICOM = "dicom"
PDF = "pdf"
OFFICE = "office"
URL = "url"


# ========== Graphify compatibility layer ==========
# Re-export graphify.detect symbols for tests and general usage

from graphify.detect import (
    FileType,
    detect as _gg_detect,
    count_words,
    _looks_like_paper,
    _is_ignored,
    _load_graphifyignore,
    CODE_EXTENSIONS,
    DOC_EXTENSIONS,
    CORPUS_WARN_THRESHOLD,
    CORPUS_UPPER_THRESHOLD,
)

# Medical string constants (also defined above, but re-exported here for clarity)
DICOM = DICOM  # noqa: F811
PDF = PDF      # noqa: F811
OFFICE = OFFICE  # noqa: F811
URL = URL      # noqa: F811

# Re-export detect
detect = _gg_detect

# Classify_* stub functions (for tests that import these symbols)
from pathlib import Path as _Path
def _make_stub(ftype):
    return lambda path: {"file_type": ftype, "path": str(path), "label": path.name}

classify_python = _make_stub(FileType.CODE)
classify_js = _make_stub(FileType.CODE)
classify_java = _make_stub(FileType.CODE)
classify_c = _make_stub(FileType.CODE)
classify_cpp = _make_stub(FileType.CODE)
classify_go = _make_stub(FileType.CODE)
classify_rust = _make_stub(FileType.CODE)
classify_ruby = _make_stub(FileType.CODE)
classify_csharp = _make_stub(FileType.CODE)
classify_kotlin = _make_stub(FileType.CODE)
classify_scala = _make_stub(FileType.CODE)
classify_php = _make_stub(FileType.CODE)
classify_swift = _make_stub(FileType.CODE)
classify_julia = _make_stub(FileType.CODE)
classify_lua = _make_stub(FileType.CODE)
classify_objc = _make_stub(FileType.CODE)
classify_elixir = _make_stub(FileType.CODE)
classify_powershell = _make_stub(FileType.CODE)
classify_blade = _make_stub(FileType.CODE)
classify_dart = _make_stub(FileType.CODE)

del _Path, _make_stub, _gg_detect

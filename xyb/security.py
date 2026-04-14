# Security helpers - re-export from graphify.security
"""This module exists for backward compatibility."""

# Re-export everything from graphify.security
from graphify.security import (
    validate_url,
    _build_opener,
    safe_fetch,
    safe_fetch_text,
    validate_graph_path,
    sanitize_label,
    # Constants (for advanced usage)
    _ALLOWED_SCHEMES,
    _MAX_FETCH_BYTES,
    _MAX_TEXT_BYTES,
    _BLOCKED_HOSTS,
    _CONTROL_CHAR_RE,
    _MAX_LABEL_LEN,
)

# Extend with any xyb-specific additions if needed in the future
# (currently none)

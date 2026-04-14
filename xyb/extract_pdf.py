"""PDF text extraction using pypdf."""
from __future__ import annotations
from pathlib import Path


def extract_pdf(path: str | Path) -> dict:
    """Extract text and metadata from a PDF file.

    Parameters
    ----------
    path : str or Path
        Path to the PDF file.

    Returns
    -------
    dict with keys:
        text          - concatenated text from all pages
        source_file   - absolute path of the source file
        page_count    - number of pages
        file_type     - always ``'pdf'``
    """
    from pypdf import PdfReader

    path = Path(path)
    reader = PdfReader(str(path))

    parts: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            parts.append(extracted)

    return {
        "text": "\n".join(parts),
        "source_file": str(path.resolve()),
        "page_count": len(reader.pages),
        "file_type": "pdf",
    }

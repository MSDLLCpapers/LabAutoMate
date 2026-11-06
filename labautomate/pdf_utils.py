"""
pdf_utils.py
PDF text extraction utilities for LabAutoMate.
Uses PyMuPDF (fitz) for reliable extraction from instrument manuals.
"""

import fitz  # PyMuPDF
from typing import Optional


def extract_pdf_text(
    pdf_data: bytes,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> str:
    """
    Extract text from a PDF file.

    Args:
        pdf_data: Raw PDF bytes (from file upload or file read).
        start_page: 0-indexed start page (None = from beginning).
        end_page: 0-indexed end page exclusive (None = to the end).

    Returns:
        Extracted text as a single string with page markers.
    """
    doc = fitz.open(stream=pdf_data, filetype="pdf")

    first = start_page if start_page is not None else 0
    last = end_page if end_page is not None else doc.page_count

    first = max(0, first)
    last = min(doc.page_count, last)

    pages = []
    for i in range(first, last):
        page = doc[i]
        text = page.get_text("text")
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text.strip()}")

    doc.close()
    return "\n\n".join(pages)

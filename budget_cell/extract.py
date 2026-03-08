"""
IO boundary: pdfplumber page → PageGeometry.

This is the only module that depends on pdfplumber.
"""

from __future__ import annotations

from typing import Sequence

import pdfplumber

from budget_cell.types import Line, PageGeometry, Word


# ---------------------------------------------------------------------------
# Pure extraction: pdfplumber page → PageGeometry
# ---------------------------------------------------------------------------

def extract_page_geometry(page: pdfplumber.page.Page) -> PageGeometry:
    """Extract lines and words from a pdfplumber page into immutable domain types."""
    raw_lines = page.lines or []
    raw_words = page.extract_words(
        keep_blank_chars=False, x_tolerance=2, y_tolerance=2
    ) or []

    return PageGeometry(
        width=float(page.width),
        height=float(page.height),
        lines=tuple(
            Line(
                x0=l["x0"], y0=l["top"], x1=l["x1"], y1=l["bottom"],
                linewidth=l.get("linewidth", 0),
            )
            for l in raw_lines
        ),
        words=tuple(
            Word(x0=w["x0"], y0=w["top"], x1=w["x1"], y1=w["bottom"], text=w["text"])
            for w in raw_words
        ),
    )


# ---------------------------------------------------------------------------
# Convenience IO wrappers
# ---------------------------------------------------------------------------

def extract_geometry_from_path(path: str, page_index: int = 0) -> PageGeometry:
    """Open PDF file and extract geometry for a single page."""
    with pdfplumber.open(path) as pdf:
        return extract_page_geometry(pdf.pages[page_index])


def extract_all_geometries(pdf_path: str) -> tuple[PageGeometry, ...]:
    """map(extract_page_geometry) over all pages."""
    with pdfplumber.open(pdf_path) as pdf:
        return tuple(map(extract_page_geometry, pdf.pages))

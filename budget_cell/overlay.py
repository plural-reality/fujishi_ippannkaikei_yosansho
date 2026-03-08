"""
IO boundary: overlay rendering with fitz (pymupdf).

This is the only module that depends on fitz.
"""

from __future__ import annotations

from typing import Sequence

import fitz

from budget_cell.types import Grid, PageGeometry


# ---------------------------------------------------------------------------
# Drawing constants
# ---------------------------------------------------------------------------

_RED = (1, 0, 0)
_BLUE = (0, 0, 1)
_GREEN = (0, 0.6, 0)


# ---------------------------------------------------------------------------
# Per-page drawing (mutates fitz page in-place)
# ---------------------------------------------------------------------------

def draw_overlay_on_fitz_page(
    fitz_page: fitz.Page,
    geom: PageGeometry,
    grid: Grid,
) -> None:
    """
    Draw detection overlay on a single fitz page.
      - Red: original PDF vector lines
      - Blue dashed: text-row boundaries
      - Green: word bounding boxes
    """
    # Red: PDF vector lines
    for line in geom.lines:
        shape = fitz_page.new_shape()
        shape.draw_line(fitz.Point(line.x0, line.y0), fitz.Point(line.x1, line.y1))
        shape.finish(color=_RED, width=1.5)
        shape.commit()

    # Blue dashed: row boundaries
    col_min = min(grid.col_boundaries) if grid.col_boundaries else 0
    col_max = max(grid.col_boundaries) if grid.col_boundaries else geom.width
    for y in grid.row_boundaries:
        shape = fitz_page.new_shape()
        shape.draw_line(fitz.Point(col_min, y), fitz.Point(col_max, y))
        shape.finish(color=_BLUE, width=0.5, dashes="[3 3]")
        shape.commit()

    # Green: word bounding boxes
    for w in geom.words:
        shape = fitz_page.new_shape()
        shape.draw_rect(fitz.Rect(w.x0, w.y0, w.x1, w.y1))
        shape.finish(color=_GREEN, width=0.3, fill=None)
        shape.commit()


# ---------------------------------------------------------------------------
# Single-page convenience
# ---------------------------------------------------------------------------

def render_overlay(
    src_pdf_bytes: bytes,
    geom: PageGeometry,
    grid: Grid,
    page_index: int = 0,
) -> bytes:
    """Render overlay on a single page and return PDF bytes."""
    doc = fitz.open(stream=src_pdf_bytes, filetype="pdf")
    draw_overlay_on_fitz_page(doc[page_index], geom, grid)
    result = doc.tobytes()
    doc.close()
    return result


# ---------------------------------------------------------------------------
# Multi-page rendering
# ---------------------------------------------------------------------------

def render_multi_overlay(
    src_path: str,
    dst_path: str,
    geoms: Sequence[PageGeometry],
    grids: Sequence[Grid],
    on_page_done=None,
) -> None:
    """Open source PDF with fitz, draw overlays on each page, save to dst."""
    doc = fitz.open(src_path)
    total = min(len(doc), len(geoms), len(grids))

    _ = tuple(
        (
            draw_overlay_on_fitz_page(doc[i], geoms[i], grids[i]),
            on_page_done(i, total) if on_page_done else None,
        )
        for i in range(total)
    )

    doc.save(dst_path)
    doc.close()


# ---------------------------------------------------------------------------
# File IO helpers
# ---------------------------------------------------------------------------

def read_pdf_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

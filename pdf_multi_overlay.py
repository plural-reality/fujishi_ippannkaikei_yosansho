"""
Multi-page PDF overlay — maps pdf_cell_detect over all pages of a PDF.

Architecture:
  pdfplumber.pages → map(extract_page_geometry) → map(build_grid)
                                                         ↓
  fitz doc → zip(pages, geoms, grids) → map(draw_overlay_on_fitz_page) → save

Depends only on pdf_cell_detect's pure functions + drawing primitive.
No budget-specific knowledge.

Usage:
  python pdf_multi_overlay.py <input.pdf> <output.pdf>
"""

from __future__ import annotations

import sys
from typing import Sequence

import fitz
import pdfplumber

from pdf_cell_detect import (
    Grid,
    PageGeometry,
    build_grid,
    draw_overlay_on_fitz_page,
    extract_page_geometry,
)


# ---------------------------------------------------------------------------
# Pure: extract all page geometries
# ---------------------------------------------------------------------------

def extract_all_geometries(pdf_path: str) -> tuple[PageGeometry, ...]:
    """map(extract_page_geometry) over all pages. Pure except for file read."""
    with pdfplumber.open(pdf_path) as pdf:
        return tuple(map(extract_page_geometry, pdf.pages))


# ---------------------------------------------------------------------------
# Pure: build all grids
# ---------------------------------------------------------------------------

def build_all_grids(geoms: Sequence[PageGeometry]) -> tuple[Grid, ...]:
    """map(build_grid) over all geometries. Fully pure."""
    return tuple(map(build_grid, geoms))


# ---------------------------------------------------------------------------
# IO: render overlays on all pages and save
# ---------------------------------------------------------------------------

def render_multi_overlay(
    src_path: str,
    dst_path: str,
    geoms: Sequence[PageGeometry],
    grids: Sequence[Grid],
    on_page_done=None,
) -> None:
    """
    Open source PDF with fitz, draw overlays on each page, save to dst.

    on_page_done: optional callback (page_index, total) for progress.
    """
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
# Top-level composition
# ---------------------------------------------------------------------------

def process_pdf(src_path: str, dst_path: str) -> None:
    """Full pipeline: extract → grid → overlay → save."""
    total_pages = fitz.open(src_path).page_count
    print(f"Processing {total_pages} pages: {src_path}")

    print("  Extracting geometries...")
    geoms = extract_all_geometries(src_path)
    print(f"  Extracted {len(geoms)} pages")

    print("  Building grids...")
    grids = build_all_grids(geoms)

    print("  Rendering overlays...")
    render_multi_overlay(
        src_path, dst_path, geoms, grids,
        on_page_done=lambda i, t: (
            print(f"    [{i + 1}/{t}]") if (i + 1) % 50 == 0 or i + 1 == t else None
        ),
    )
    print(f"  Saved: {dst_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    usage = "Usage: python pdf_multi_overlay.py <input.pdf> <output.pdf>"
    src = sys.argv[1] if len(sys.argv) > 1 else None
    dst = sys.argv[2] if len(sys.argv) > 2 else None

    _ = (
        process_pdf(src, dst) if src and dst else
        (print(usage), sys.exit(1))
    )


if __name__ == "__main__":
    main()

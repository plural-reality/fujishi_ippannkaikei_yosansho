"""
CLI: Multi-page PDF overlay generation.

Usage:
  python -m budget_cell.cli.overlay <input.pdf> <output.pdf>
"""

from __future__ import annotations

import sys

import fitz

from budget_cell.extract import extract_all_geometries
from budget_cell.grid import build_grid
from budget_cell.overlay import render_multi_overlay


def process_pdf(src_path: str, dst_path: str) -> None:
    """Full pipeline: extract → grid → overlay → save."""
    total_pages = fitz.open(src_path).page_count
    print(f"Processing {total_pages} pages: {src_path}")

    print("  Extracting geometries...")
    geoms = extract_all_geometries(src_path)
    print(f"  Extracted {len(geoms)} pages")

    print("  Building grids...")
    grids = tuple(map(build_grid, geoms))

    print("  Rendering overlays...")
    render_multi_overlay(
        src_path, dst_path, geoms, grids,
        on_page_done=lambda i, t: (
            print(f"    [{i + 1}/{t}]") if (i + 1) % 50 == 0 or i + 1 == t else None
        ),
    )
    print(f"  Saved: {dst_path}")


def main() -> None:
    usage = "Usage: python -m budget_cell.cli.overlay <input.pdf> <output.pdf>"
    src = sys.argv[1] if len(sys.argv) > 1 else None
    dst = sys.argv[2] if len(sys.argv) > 2 else None

    _ = (
        process_pdf(src, dst) if src and dst else
        (print(usage), sys.exit(1))
    )


if __name__ == "__main__":
    main()

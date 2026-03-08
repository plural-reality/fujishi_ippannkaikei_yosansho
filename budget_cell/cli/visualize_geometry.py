"""
CLI: visualize geometry layers on PDF pages.

Color mapping:
  - Red: vector lines
  - Blue: inferred grid boundaries (rows + columns)
  - Orange: assigned cell boxes
  - Green: word bounding boxes
"""

from __future__ import annotations

import argparse
import sys

import fitz

from budget_cell.cells import assign_words_to_cells
from budget_cell.extract import extract_all_geometries
from budget_cell.grid import build_grid


_RED = (1, 0, 0)
_BLUE = (0, 0, 1)
_ORANGE = (1, 0.5, 0)
_GREEN = (0, 0.6, 0)


def _indices(total: int, start_page: int, end_page: int | None) -> tuple[int, ...]:
    start = max(start_page - 1, 0)
    end = total if end_page is None else min(end_page, total)
    return tuple(range(start, end))


def _draw_page(page: fitz.Page, geom, grid, cells) -> None:
    for line in geom.lines:
        shape = page.new_shape()
        shape.draw_line(fitz.Point(line.x0, line.y0), fitz.Point(line.x1, line.y1))
        shape.finish(color=_RED, width=1.2)
        shape.commit()

    if grid.col_boundaries:
        y_min = min(grid.row_boundaries) if grid.row_boundaries else 0
        y_max = max(grid.row_boundaries) if grid.row_boundaries else geom.height
        for x in grid.col_boundaries:
            shape = page.new_shape()
            shape.draw_line(fitz.Point(x, y_min), fitz.Point(x, y_max))
            shape.finish(color=_BLUE, width=0.5, dashes="[2 2]")
            shape.commit()

    if grid.row_boundaries:
        x_min = min(grid.col_boundaries) if grid.col_boundaries else 0
        x_max = max(grid.col_boundaries) if grid.col_boundaries else geom.width
        for y in grid.row_boundaries:
            shape = page.new_shape()
            shape.draw_line(fitz.Point(x_min, y), fitz.Point(x_max, y))
            shape.finish(color=_BLUE, width=0.5, dashes="[2 2]")
            shape.commit()

    for cell in cells:
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(cell.x0, cell.y0, cell.x1, cell.y1))
        shape.finish(color=_ORANGE, width=0.4)
        shape.commit()

    for word in geom.words:
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(word.x0, word.y0, word.x1, word.y1))
        shape.finish(color=_GREEN, width=0.3)
        shape.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.visualize_geometry",
        description="Overlay line/cell/text geometry on PDF pages.",
    )
    parser.add_argument("src", help="input PDF path")
    parser.add_argument("dst", help="output PDF path")
    parser.add_argument("--start-page", type=int, default=1, help="1-based start page")
    parser.add_argument("--end-page", type=int, default=None, help="1-based end page (inclusive)")
    args = parser.parse_args(sys.argv[1:])

    print(f"Extracting geometries: {args.src}")
    geoms = extract_all_geometries(args.src)
    grids = tuple(map(build_grid, geoms))
    cells_by_page = tuple(assign_words_to_cells(g, gr) for g, gr in zip(geoms, grids))

    doc = fitz.open(args.src)
    selected = _indices(len(doc), args.start_page, args.end_page)
    for i in selected:
        _draw_page(doc[i], geoms[i], grids[i], cells_by_page[i])
    doc.save(args.dst)
    doc.close()
    print(f"Saved visualization: {args.dst} (pages={len(selected)})")


if __name__ == "__main__":
    main()

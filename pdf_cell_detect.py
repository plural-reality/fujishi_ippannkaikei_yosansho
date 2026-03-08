"""
PDF Cell Detection — pdfplumber ベクター罫線 + テキスト Y 座標クラスタリングによるセル認識

Architecture:
  PDF bytes → extract_page_geometry (pure) → PageGeometry
  PageGeometry → build_grid (pure) → Grid (columns × rows)
  Grid + words → assign_words_to_cells (pure) → list[Cell]
  PageGeometry → render_overlay (IO boundary) → PDF bytes

All intermediate types are frozen dataclasses (immutable).
IO is confined to read_pdf / write_overlay at the edges.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import IO, Sequence

import fitz  # pymupdf
import pdfplumber


# ---------------------------------------------------------------------------
# Domain types (immutable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Line:
    x0: float
    y0: float
    x1: float
    y1: float
    linewidth: float

    @property
    def is_vertical(self) -> bool:
        return abs(self.x1 - self.x0) < 1.0

    @property
    def is_horizontal(self) -> bool:
        return abs(self.y1 - self.y0) < 1.0


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class PageGeometry:
    width: float
    height: float
    lines: tuple[Line, ...]
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Grid:
    col_boundaries: tuple[float, ...]   # sorted X positions
    row_boundaries: tuple[float, ...]   # sorted Y positions (top of each row)


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


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
# Pure grid construction
# ---------------------------------------------------------------------------

def _cluster_values(values: Sequence[float], threshold: float) -> tuple[float, ...]:
    """Merge nearby float values into clusters, returning representative (min) of each."""
    sorted_vals = sorted(values)
    clusters: list[float] = []
    for v in sorted_vals:
        clusters = (
            clusters
            if clusters and v - clusters[-1] <= threshold
            else [*clusters, v]
        )
    return tuple(clusters)


def _vertical_line_xs(lines: Sequence[Line]) -> tuple[float, ...]:
    """Extract unique X positions from vertical lines."""
    return tuple(sorted({round(l.x0, 1) for l in lines if l.is_vertical}))


def _horizontal_line_ys(lines: Sequence[Line]) -> tuple[float, ...]:
    """Extract unique Y positions from horizontal lines."""
    return tuple(sorted({round(l.y0, 1) for l in lines if l.is_horizontal}))


def _word_row_ys(words: Sequence[Word], threshold: float = 3.0) -> tuple[float, ...]:
    """Cluster word top-Y positions into row boundaries."""
    tops = [round(w.y0, 1) for w in words]
    return _cluster_values(tops, threshold) if tops else ()


def build_grid(
    geom: PageGeometry,
    row_cluster_threshold: float = 3.0,
) -> Grid:
    """
    Build a Grid from PageGeometry.

    Column boundaries come from vertical PDF lines.
    Row boundaries come from text Y-coordinate clustering
    (since horizontal row dividers are typically absent in budget PDFs).
    """
    col_boundaries = _vertical_line_xs(geom.lines)
    pdf_h_lines = _horizontal_line_ys(geom.lines)

    # Determine table vertical extent from horizontal lines
    table_top = min(pdf_h_lines) if pdf_h_lines else 0.0
    table_bottom = max(pdf_h_lines) if pdf_h_lines else geom.height

    # Row boundaries from word Y clusters, filtered to table region
    all_row_ys = _word_row_ys(geom.words, row_cluster_threshold)
    row_boundaries = tuple(
        y for y in all_row_ys if table_top - 5 <= y <= table_bottom + 5
    )

    return Grid(col_boundaries=col_boundaries, row_boundaries=row_boundaries)


# ---------------------------------------------------------------------------
# Pure cell assignment
# ---------------------------------------------------------------------------

def _find_column(x_mid: float, col_boundaries: Sequence[float]) -> int:
    """Find which column a horizontal midpoint falls into. Returns -1 if outside."""
    return next(
        (
            i
            for i in range(len(col_boundaries) - 1)
            if col_boundaries[i] <= x_mid < col_boundaries[i + 1]
        ),
        -1,
    )


def _find_row(y_top: float, row_boundaries: Sequence[float], tolerance: float = 5.0) -> int:
    """Find which row a word's top-Y belongs to. Returns -1 if no match."""
    return next(
        (
            i
            for i, ry in enumerate(row_boundaries)
            if abs(y_top - ry) <= tolerance
        ),
        -1,
    )


def _row_bottom(row_idx: int, row_boundaries: Sequence[float], page_bottom: float) -> float:
    """Compute the bottom edge of a row."""
    return (
        row_boundaries[row_idx + 1]
        if row_idx + 1 < len(row_boundaries)
        else page_bottom
    )


def assign_words_to_cells(
    geom: PageGeometry,
    grid: Grid,
    row_tolerance: float = 5.0,
) -> tuple[Cell, ...]:
    """Assign each word to a (row, col) cell. Words outside the grid are dropped."""
    cell_map: dict[tuple[int, int], list[Word]] = {}

    for w in geom.words:
        x_mid = (w.x0 + w.x1) / 2.0
        col = _find_column(x_mid, grid.col_boundaries)
        row = _find_row(w.y0, grid.row_boundaries, row_tolerance)
        cell_map = (
            {**cell_map, (row, col): [*cell_map.get((row, col), []), w]}
            if row >= 0 and col >= 0
            else cell_map
        )

    page_bottom = max((y for y in grid.row_boundaries), default=geom.height) + 20

    return tuple(
        Cell(
            row=r,
            col=c,
            x0=grid.col_boundaries[c],
            y0=grid.row_boundaries[r],
            x1=grid.col_boundaries[c + 1] if c + 1 < len(grid.col_boundaries) else geom.width,
            y1=_row_bottom(r, grid.row_boundaries, page_bottom),
            text=" ".join(w.text for w in sorted(words, key=lambda w: w.x0)),
        )
        for (r, c), words in sorted(cell_map.items())
    )


# ---------------------------------------------------------------------------
# IO boundary: overlay rendering
# ---------------------------------------------------------------------------

_RED = (1, 0, 0)
_BLUE = (0, 0, 1)
_GREEN = (0, 0.6, 0)


def render_overlay(
    src_pdf_bytes: bytes,
    geom: PageGeometry,
    grid: Grid,
    page_index: int = 0,
) -> bytes:
    """
    Render an overlay on the source PDF:
      - Red: original PDF vector lines
      - Blue dashed: text-row boundaries
      - Green: word bounding boxes
    Returns the modified PDF as bytes.
    """
    doc = fitz.open(stream=src_pdf_bytes, filetype="pdf")
    fitz_page = doc[page_index]

    # Red: PDF vector lines
    for line in geom.lines:
        shape = fitz_page.new_shape()
        shape.draw_line(fitz.Point(line.x0, line.y0), fitz.Point(line.x1, line.y1))
        shape.finish(color=_RED, width=1.5)
        shape.commit()

    # Blue dashed: row boundaries across each table region
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

    result = doc.tobytes()
    doc.close()
    return result


# ---------------------------------------------------------------------------
# IO boundary: file read/write
# ---------------------------------------------------------------------------

def read_pdf_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def write_bytes(data: bytes, path: str) -> None:
    with open(path, "wb") as f:
        f.write(data)


def extract_geometry_from_path(path: str, page_index: int = 0) -> PageGeometry:
    """Convenience: open PDF file and extract geometry for a single page."""
    with pdfplumber.open(path) as pdf:
        return extract_page_geometry(pdf.pages[page_index])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    usage = (
        "Usage: python pdf_cell_detect.py <input.pdf> [--page N] [--overlay out.pdf] [--json out.json]\n"
        "  --page N       Page number (0-indexed, default: 0)\n"
        "  --overlay FILE  Output overlay PDF\n"
        "  --json FILE     Output cell data as JSON"
    )

    input_pdf = args[0] if args else None
    page_index = 0
    overlay_path = None
    json_path = None

    i = 1
    while i < len(args):
        (
            _set_page := lambda: None,  # placeholder
        )
        arg = args[i]
        remaining = args[i + 1] if i + 1 < len(args) else None

        page_index, overlay_path, json_path, i = (
            (int(remaining), overlay_path, json_path, i + 2) if arg == "--page" and remaining else
            (page_index, remaining, json_path, i + 2) if arg == "--overlay" and remaining else
            (page_index, overlay_path, remaining, i + 2) if arg == "--json" and remaining else
            (page_index, overlay_path, json_path, i + 1)
        )

    if not input_pdf:
        print(usage)
        sys.exit(1)

    # Extract
    geom = extract_geometry_from_path(input_pdf, page_index)
    grid = build_grid(geom)
    cells = assign_words_to_cells(geom, grid)

    print(f"Page {page_index}: {geom.width}x{geom.height}")
    print(f"  Lines: {len(geom.lines)}, Words: {len(geom.words)}")
    print(f"  Columns: {len(grid.col_boundaries)}, Rows: {len(grid.row_boundaries)}")
    print(f"  Cells: {len(cells)}")

    # Overlay
    _ = (
        write_bytes(
            render_overlay(read_pdf_bytes(input_pdf), geom, grid, page_index),
            overlay_path,
        )
        or print(f"  Overlay: {overlay_path}")
    ) if overlay_path else None

    # JSON
    _ = (
        _write_cells_json(cells, grid, json_path)
        or print(f"  JSON: {json_path}")
    ) if json_path else None


def _write_cells_json(cells: tuple[Cell, ...], grid: Grid, path: str) -> None:
    import json
    data = {
        "grid": {
            "col_boundaries": list(grid.col_boundaries),
            "row_boundaries": list(grid.row_boundaries),
        },
        "cells": [
            {
                "row": c.row, "col": c.col,
                "bbox": {"x0": c.x0, "y0": c.y0, "x1": c.x1, "y1": c.y1},
                "text": c.text,
            }
            for c in cells
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

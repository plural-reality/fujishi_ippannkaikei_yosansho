"""
Pure cell assignment: PageGeometry × Grid → Cell[].

Maps words to (row, col) cells. No IO.
"""

from __future__ import annotations

from typing import Sequence

from budget_cell.types import Cell, Grid, PageGeometry, Word


# ---------------------------------------------------------------------------
# Lookup helpers
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


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

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

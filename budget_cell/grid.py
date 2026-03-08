"""
Pure grid construction: PageGeometry → Grid.

Column boundaries from vertical PDF lines, row boundaries from text Y-clustering.
No IO, no external dependencies beyond types.
"""

from __future__ import annotations

from typing import Sequence

from budget_cell.types import Grid, Line, PageGeometry, Word


# ---------------------------------------------------------------------------
# Clustering
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


# ---------------------------------------------------------------------------
# Line extraction
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Grid construction
# ---------------------------------------------------------------------------

def build_grid(
    geom: PageGeometry,
    row_cluster_threshold: float = 3.0,
) -> Grid:
    """
    Build a Grid from PageGeometry.

    Column boundaries come from vertical PDF lines.
    Row boundaries come from text Y-coordinate clustering.
    """
    col_boundaries = _vertical_line_xs(geom.lines)
    pdf_h_lines = _horizontal_line_ys(geom.lines)

    table_top = min(pdf_h_lines) if pdf_h_lines else 0.0
    table_bottom = max(pdf_h_lines) if pdf_h_lines else geom.height

    all_row_ys = _word_row_ys(geom.words, row_cluster_threshold)
    row_boundaries = tuple(
        y for y in all_row_ys if table_top - 5 <= y <= table_bottom + 5
    )

    return Grid(col_boundaries=col_boundaries, row_boundaries=row_boundaries)

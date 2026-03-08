"""
Pure grid construction: PageGeometry → Grid.

Column boundaries from vertical PDF lines, row boundaries from text Y-clustering.
No IO, no external dependencies beyond types.

Also provides expenditure section detection via 扉ページ (title page).
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


# ---------------------------------------------------------------------------
# Section detection: 扉ページ (title page) based
# ---------------------------------------------------------------------------

def _is_title_page(geom: PageGeometry, title: str) -> bool:
    """A title page has no lines and its only text matches the given title."""
    text = " ".join(w.text for w in geom.words).strip()
    return len(geom.lines) == 0 and text == title


def _find_title_page(geoms: Sequence[PageGeometry], title: str) -> int | None:
    """Return the index of the first page whose text is exactly `title`, or None."""
    return next(
        (i for i, g in enumerate(geoms) if _is_title_page(g, title)),
        None,
    )


def is_expenditure_page(geom: PageGeometry) -> bool:
    """Expenditure (歳出) data pages have vertical vector lines forming table columns."""
    return any(l.is_vertical for l in geom.lines)


def extract_expenditure_pages(
    geoms: Sequence[PageGeometry],
) -> tuple[PageGeometry, ...]:
    """Slice geometries to expenditure section: from 「歳 出」title page onward, table pages only."""
    start = _find_title_page(geoms, "歳 出")
    section = geoms[start:] if start is not None else geoms
    return tuple(g for g in section if is_expenditure_page(g))

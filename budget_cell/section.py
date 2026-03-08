"""
Pure mid-page section split: detect 項 transitions within a single page's cells.

A page can contain data for multiple (款, 項) sections when a subtotal row
("計 N款 ...") is followed by a new section header ("N項 ...").

This module splits a page's cells at those boundaries, producing one or more
(PageHeader, cells) segments.

Depends only on types + re. No IO.
"""

from __future__ import annotations

import re
from typing import Sequence

from budget_cell.types import Cell, PageHeader


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

_SUBTOTAL_RE = re.compile(r"^計\s")
_KOU_TRANSITION_RE = re.compile(r"^([０-９\d]+)項$")

COL_MOKU = 0
COL_HONENDO = 1


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _cell_text(cells: Sequence[Cell], row: int, col: int) -> str:
    return next(
        (c.text.strip() for c in cells if c.row == row and c.col == col),
        "",
    )


def _unique_rows(cells: Sequence[Cell]) -> tuple[int, ...]:
    return tuple(sorted({c.row for c in cells}))


def _is_subtotal_row(cells: Sequence[Cell], row: int) -> bool:
    text = _cell_text(cells, row, COL_MOKU)
    return bool(_SUBTOTAL_RE.match(text))


def _is_kou_transition_row(cells: Sequence[Cell], row: int) -> tuple[str, str] | None:
    """If row is a 項 transition header, return (kou_number, kou_name). Else None."""
    moku_text = _cell_text(cells, row, COL_MOKU)
    m = _KOU_TRANSITION_RE.match(moku_text)
    return (
        (m.group(1), _cell_text(cells, row, COL_HONENDO))
        if m is not None
        else None
    )


def _cells_in_rows(cells: Sequence[Cell], rows: frozenset[int]) -> tuple[Cell, ...]:
    return tuple(c for c in cells if c.row in rows)


# ---------------------------------------------------------------------------
# Split logic
# ---------------------------------------------------------------------------

def split_page_sections(
    header: PageHeader,
    cells: Sequence[Cell],
) -> tuple[tuple[PageHeader, tuple[Cell, ...]], ...]:
    """Split a page's cells at mid-page 項 transitions.

    Returns one or more (PageHeader, cells) segments.
    Normal pages (no transition) → single segment.
    Transition pages → pre-transition segment + post-transition segment(s).
    """
    rows = _unique_rows(cells)
    split_points = _find_split_points(cells, rows)

    return (
        ((header, tuple(cells)),)
        if not split_points
        else _split_at(header, cells, rows, split_points)
    )


def _find_split_points(
    cells: Sequence[Cell],
    rows: tuple[int, ...],
) -> tuple[tuple[int, int, str, str], ...]:
    """Find (subtotal_row, transition_row, kou_number, kou_name) tuples."""
    points: list[tuple[int, int, str, str]] = []
    for i, r in enumerate(rows):
        if _is_subtotal_row(cells, r):
            # Look ahead for a 項 transition row
            for j in range(i + 1, len(rows)):
                kou = _is_kou_transition_row(cells, rows[j])
                if kou is not None:
                    points.append((r, rows[j], kou[0], kou[1]))
                    break
    return tuple(points)


def _split_at(
    header: PageHeader,
    cells: Sequence[Cell],
    rows: tuple[int, ...],
    split_points: tuple[tuple[int, int, str, str], ...],
) -> tuple[tuple[PageHeader, tuple[Cell, ...]], ...]:
    """Split cells into segments at the given split points."""
    # Collect rows to exclude (subtotal + transition rows)
    exclude_rows = frozenset(
        r for sub_r, trans_r, _, _ in split_points for r in (sub_r, trans_r)
    )

    # Build boundary list: row indices where new sections start (first data row after transition)
    boundaries: list[tuple[int, PageHeader]] = []
    for sub_r, trans_r, kou_num, kou_name in split_points:
        # First row after the transition row
        data_start = next(
            (r for r in rows if r > trans_r and r not in exclude_rows),
            None,
        )
        if data_start is not None:
            new_header = PageHeader(
                kan_number=header.kan_number,
                kan_name=header.kan_name,
                kou_number=kou_num,
                kou_name=kou_name,
            )
            boundaries.append((data_start, new_header))

    # Build segments
    all_data_rows = tuple(r for r in rows if r not in exclude_rows)
    segments: list[tuple[PageHeader, tuple[Cell, ...]]] = []
    current_header = header
    current_start = 0

    for boundary_row, new_header in boundaries:
        seg_rows = frozenset(
            r for r in all_data_rows[current_start:]
            if r < boundary_row
        )
        seg_cells = _cells_in_rows(cells, seg_rows)
        if seg_cells:
            segments.append((current_header, seg_cells))
        current_header = new_header
        current_start = next(
            (i for i, r in enumerate(all_data_rows) if r >= boundary_row),
            len(all_data_rows),
        )

    # Final segment
    remaining_rows = frozenset(all_data_rows[current_start:])
    remaining_cells = _cells_in_rows(cells, remaining_rows)
    if remaining_cells:
        segments.append((current_header, remaining_cells))

    return tuple(segments)

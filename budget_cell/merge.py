"""
Pure row merge: Cell[] → Cell[] with logical rows.

Merges text-only continuation rows into the preceding logical row.
Left table and right table have INDEPENDENT row structures:
  - Left table (cols 0-7): anchor = col 1 (本年度予算額)
  - Right table (cols 9-11): anchor = col 10 (金額)

Each column group is merged independently, then recombined.
This handles the case where 目 name wraps while 節 starts a new entry.

Depends only on types. No IO.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from budget_cell.types import Cell, Word


# ---------------------------------------------------------------------------
# Column groups with their anchor columns
# ---------------------------------------------------------------------------

_LEFT_COLS: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5, 6, 7})
_LEFT_ANCHOR: frozenset[int] = frozenset({1})   # 本年度予算額

_RIGHT_COLS: frozenset[int] = frozenset({9, 10, 11})
_RIGHT_ANCHOR: frozenset[int] = frozenset({10}) # 金額

_COLUMN_GROUPS: tuple[tuple[frozenset[int], frozenset[int]], ...] = (
    (_LEFT_COLS, _LEFT_ANCHOR),
    (_RIGHT_COLS, _RIGHT_ANCHOR),
)


# ---------------------------------------------------------------------------
# Core merge logic
# ---------------------------------------------------------------------------

def _cell_index(cells: Sequence[Cell]) -> Mapping[tuple[int, int], Cell]:
    return {(c.row, c.col): c for c in cells}


def _unique_rows(cells: Sequence[Cell]) -> tuple[int, ...]:
    return tuple(sorted({c.row for c in cells}))


def _row_has_anchor(
    idx: Mapping[tuple[int, int], Cell],
    row: int,
    anchor_cols: frozenset[int],
) -> bool:
    """True if this row has non-empty content in any anchor column."""
    return any(
        (row, col) in idx and idx[(row, col)].text.strip()
        for col in anchor_cols
    )


def _merge_cell_pair(base: Cell, cont: Cell) -> Cell:
    """Merge a continuation cell into the base cell (same column)."""
    return Cell(
        row=base.row,
        col=base.col,
        x0=base.x0,
        y0=base.y0,
        x1=max(base.x1, cont.x1),
        y1=max(base.y1, cont.y1),
        text=(base.text + " " + cont.text).strip() if cont.text.strip() else base.text,
        words=(*base.words, *cont.words),
    )


def _merge_column_group(
    cells: Sequence[Cell],
    all_rows: tuple[int, ...],
    group_cols: frozenset[int],
    anchor_cols: frozenset[int],
) -> tuple[Cell, ...]:
    """Merge rows within one column group based on its anchor columns."""
    group_cells = tuple(c for c in cells if c.col in group_cols)
    idx = _cell_index(group_cells)

    # Build row mapping: continuation → logical row
    row_map: dict[int, int] = {}
    current_logical: int | None = None
    for r in all_rows:
        # Check if this row has any cells in this group at all
        has_group_data = any((r, c) in idx for c in group_cols)
        if not has_group_data:
            continue
        if _row_has_anchor(idx, r, anchor_cols) or current_logical is None:
            current_logical = r
        row_map[r] = current_logical

    # Merge cells by (logical_row, col)
    merged: dict[tuple[int, int], Cell] = {}
    for cell in sorted(group_cells, key=lambda c: (c.row, c.col)):
        logical_row = row_map.get(cell.row, cell.row)
        key = (logical_row, cell.col)
        merged[key] = (
            _merge_cell_pair(merged[key], cell)
            if key in merged
            else Cell(
                row=logical_row, col=cell.col,
                x0=cell.x0, y0=cell.y0, x1=cell.x1, y1=cell.y1,
                text=cell.text, words=cell.words,
            )
        )

    return tuple(merged[k] for k in sorted(merged.keys()))


def merge_rows(
    cells: Sequence[Cell],
    column_groups: tuple[tuple[frozenset[int], frozenset[int]], ...] = _COLUMN_GROUPS,
) -> tuple[Cell, ...]:
    """Merge continuation rows independently per column group.

    Left table and right table have independent row structures,
    so each group is merged by its own anchor columns.
    """
    rows = _unique_rows(cells)
    return tuple(
        sorted(
            (
                cell
                for group_cols, anchor_cols in column_groups
                for cell in _merge_column_group(cells, rows, group_cols, anchor_cols)
            ),
            key=lambda c: (c.row, c.col),
        )
    )

"""
Tests for budget_cell.cells — pure cell assignment.
"""

from __future__ import annotations

import pytest

from budget_cell.types import Cell, Grid, Line, PageGeometry, Word
from budget_cell.cells import _find_column, _find_row, _row_bottom, assign_words_to_cells
from budget_cell.grid import build_grid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LINES = (
    Line(x0=10, y0=0, x1=10, y1=100, linewidth=0.5),
    Line(x0=50, y0=0, x1=50, y1=100, linewidth=0.5),
    Line(x0=100, y0=0, x1=100, y1=100, linewidth=0.5),
    Line(x0=10, y0=0, x1=100, y1=0, linewidth=0.5),
    Line(x0=10, y0=100, x1=100, y1=100, linewidth=0.5),
)

SAMPLE_WORDS = (
    Word(x0=12, y0=10, x1=28, y1=18, text="Hello"),
    Word(x0=52, y0=10, x1=78, y1=18, text="World"),
    Word(x0=12, y0=30, x1=28, y1=38, text="Foo"),
    Word(x0=52, y0=30.5, x1=78, y1=38.5, text="Bar"),
    Word(x0=52, y0=30, x1=60, y1=38, text="Baz"),
)

SAMPLE_GEOM = PageGeometry(
    width=120, height=120,
    lines=SAMPLE_LINES,
    words=SAMPLE_WORDS,
)


# ---------------------------------------------------------------------------
# _find_column / _find_row
# ---------------------------------------------------------------------------

class TestFindColumn:
    def test_in_first_col(self) -> None:
        assert _find_column(25.0, (10.0, 50.0, 100.0)) == 0

    def test_in_second_col(self) -> None:
        assert _find_column(75.0, (10.0, 50.0, 100.0)) == 1

    def test_outside_left(self) -> None:
        assert _find_column(5.0, (10.0, 50.0, 100.0)) == -1

    def test_on_boundary(self) -> None:
        assert _find_column(50.0, (10.0, 50.0, 100.0)) == 1


class TestFindRow:
    def test_exact_match(self) -> None:
        assert _find_row(10.0, (10.0, 30.0), tolerance=5.0) == 0

    def test_within_tolerance(self) -> None:
        assert _find_row(12.0, (10.0, 30.0), tolerance=5.0) == 0

    def test_no_match(self) -> None:
        assert _find_row(20.0, (10.0, 30.0), tolerance=5.0) == -1


# ---------------------------------------------------------------------------
# _row_bottom
# ---------------------------------------------------------------------------

class TestRowBottom:
    def test_mid_row(self) -> None:
        assert _row_bottom(0, (10.0, 30.0, 50.0), 100.0) == 30.0

    def test_last_row(self) -> None:
        assert _row_bottom(2, (10.0, 30.0, 50.0), 100.0) == 100.0


# ---------------------------------------------------------------------------
# assign_words_to_cells
# ---------------------------------------------------------------------------

class TestAssignWordsToCells:
    def test_basic_assignment(self) -> None:
        grid = build_grid(SAMPLE_GEOM)
        cells = assign_words_to_cells(SAMPLE_GEOM, grid)
        assert len(cells) > 0
        assert all(c.row >= 0 and c.col >= 0 for c in cells)

    def test_cell_text_concatenation(self) -> None:
        grid = build_grid(SAMPLE_GEOM)
        cells = assign_words_to_cells(SAMPLE_GEOM, grid)
        row1_col1 = [c for c in cells if c.row == 1 and c.col == 1]
        assert len(row1_col1) == 1
        assert "Baz" in row1_col1[0].text
        assert "Bar" in row1_col1[0].text

    def test_no_words_outside_grid(self) -> None:
        outside_word = Word(x0=200, y0=200, x1=220, y1=210, text="Outside")
        geom = PageGeometry(
            width=300, height=300,
            lines=SAMPLE_LINES,
            words=(*SAMPLE_WORDS, outside_word),
        )
        grid = build_grid(geom)
        cells = assign_words_to_cells(geom, grid)
        assert all("Outside" not in c.text for c in cells)

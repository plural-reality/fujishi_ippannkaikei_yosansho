"""
Tests for budget_cell.grid — pure grid construction functions.
"""

from __future__ import annotations

import pytest

from budget_cell.types import Grid, Line, PageGeometry, Word
from budget_cell.grid import (
    _cluster_values,
    _horizontal_line_ys,
    _vertical_line_xs,
    _word_row_ys,
    build_grid,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LINES = (
    Line(x0=10, y0=0, x1=10, y1=100, linewidth=0.5),   # vertical at x=10
    Line(x0=50, y0=0, x1=50, y1=100, linewidth=0.5),   # vertical at x=50
    Line(x0=100, y0=0, x1=100, y1=100, linewidth=0.5),  # vertical at x=100
    Line(x0=10, y0=0, x1=100, y1=0, linewidth=0.5),     # horizontal at y=0
    Line(x0=10, y0=100, x1=100, y1=100, linewidth=0.5), # horizontal at y=100
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
# _cluster_values
# ---------------------------------------------------------------------------

class TestClusterValues:
    def test_empty(self) -> None:
        assert _cluster_values([], 3.0) == ()

    def test_single(self) -> None:
        assert _cluster_values([5.0], 3.0) == (5.0,)

    def test_merges_nearby(self) -> None:
        assert _cluster_values([10.0, 11.0, 12.0, 20.0, 21.0], 3.0) == (10.0, 20.0)

    def test_keeps_distant(self) -> None:
        assert _cluster_values([1.0, 10.0, 20.0], 3.0) == (1.0, 10.0, 20.0)

    def test_unsorted_input(self) -> None:
        assert _cluster_values([20.0, 1.0, 10.0], 3.0) == (1.0, 10.0, 20.0)


# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------

class TestLineClassification:
    def test_vertical_lines(self) -> None:
        assert _vertical_line_xs(SAMPLE_LINES) == (10.0, 50.0, 100.0)

    def test_horizontal_lines(self) -> None:
        assert _horizontal_line_ys(SAMPLE_LINES) == (0.0, 100.0)


# ---------------------------------------------------------------------------
# _word_row_ys
# ---------------------------------------------------------------------------

class TestWordRowYs:
    def test_clusters_words(self) -> None:
        rows = _word_row_ys(SAMPLE_WORDS, threshold=3.0)
        assert len(rows) == 2
        assert rows[0] == 10.0
        assert rows[1] == 30.0

    def test_empty(self) -> None:
        assert _word_row_ys((), 3.0) == ()


# ---------------------------------------------------------------------------
# build_grid
# ---------------------------------------------------------------------------

class TestBuildGrid:
    def test_grid_from_sample(self) -> None:
        grid = build_grid(SAMPLE_GEOM)
        assert grid.col_boundaries == (10.0, 50.0, 100.0)
        assert len(grid.row_boundaries) == 2
        assert 10.0 in grid.row_boundaries
        assert 30.0 in grid.row_boundaries

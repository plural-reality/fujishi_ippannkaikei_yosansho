"""
Tests for pdf_cell_detect — pure function unit tests + integration test with 106.pdf
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdf_cell_detect import (
    Cell,
    Grid,
    Line,
    PageGeometry,
    Word,
    _cluster_values,
    _find_column,
    _find_row,
    _row_bottom,
    _vertical_line_xs,
    _horizontal_line_ys,
    _word_row_ys,
    assign_words_to_cells,
    build_grid,
    extract_geometry_from_path,
    read_pdf_bytes,
    render_overlay,
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
    Word(x0=52, y0=30, x1=60, y1=38, text="Baz"),  # same row/col as Bar
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
        xs = _vertical_line_xs(SAMPLE_LINES)
        assert xs == (10.0, 50.0, 100.0)

    def test_horizontal_lines(self) -> None:
        ys = _horizontal_line_ys(SAMPLE_LINES)
        assert ys == (0.0, 100.0)


# ---------------------------------------------------------------------------
# _word_row_ys
# ---------------------------------------------------------------------------

class TestWordRowYs:
    def test_clusters_words(self) -> None:
        rows = _word_row_ys(SAMPLE_WORDS, threshold=3.0)
        # y=10 and y=30/30.5 → 2 clusters
        assert len(rows) == 2
        assert rows[0] == 10.0
        assert rows[1] == 30.0

    def test_empty(self) -> None:
        assert _word_row_ys((), 3.0) == ()


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
        # x_mid == col_boundary → belongs to that column
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
# build_grid
# ---------------------------------------------------------------------------

class TestBuildGrid:
    def test_grid_from_sample(self) -> None:
        grid = build_grid(SAMPLE_GEOM)
        assert grid.col_boundaries == (10.0, 50.0, 100.0)
        assert len(grid.row_boundaries) == 2
        assert 10.0 in grid.row_boundaries
        assert 30.0 in grid.row_boundaries


# ---------------------------------------------------------------------------
# assign_words_to_cells
# ---------------------------------------------------------------------------

class TestAssignWordsToCells:
    def test_basic_assignment(self) -> None:
        grid = build_grid(SAMPLE_GEOM)
        cells = assign_words_to_cells(SAMPLE_GEOM, grid)
        assert len(cells) > 0

        # All cells should have valid row/col
        assert all(c.row >= 0 and c.col >= 0 for c in cells)

    def test_cell_text_concatenation(self) -> None:
        """Words in the same cell should be joined by space, sorted by x0."""
        grid = build_grid(SAMPLE_GEOM)
        cells = assign_words_to_cells(SAMPLE_GEOM, grid)

        # "Baz" (x0=52) and "Bar" (x0=52, y0=30.5) are in same cell (row=1, col=1)
        row1_col1 = [c for c in cells if c.row == 1 and c.col == 1]
        assert len(row1_col1) == 1
        # Both Baz and Bar should be in this cell
        assert "Baz" in row1_col1[0].text
        assert "Bar" in row1_col1[0].text

    def test_no_words_outside_grid(self) -> None:
        """Words outside the grid should not appear in any cell."""
        outside_word = Word(x0=200, y0=200, x1=220, y1=210, text="Outside")
        geom = PageGeometry(
            width=300, height=300,
            lines=SAMPLE_LINES,
            words=(*SAMPLE_WORDS, outside_word),
        )
        grid = build_grid(geom)
        cells = assign_words_to_cells(geom, grid)
        assert all("Outside" not in c.text for c in cells)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_line_frozen(self) -> None:
        line = Line(x0=0, y0=0, x1=10, y1=10, linewidth=1)
        with pytest.raises(AttributeError):
            line.x0 = 5  # type: ignore[misc]

    def test_word_frozen(self) -> None:
        word = Word(x0=0, y0=0, x1=10, y1=10, text="hi")
        with pytest.raises(AttributeError):
            word.text = "bye"  # type: ignore[misc]

    def test_cell_frozen(self) -> None:
        cell = Cell(row=0, col=0, x0=0, y0=0, x1=10, y1=10, text="hi")
        with pytest.raises(AttributeError):
            cell.text = "bye"  # type: ignore[misc]

    def test_grid_frozen(self) -> None:
        grid = Grid(col_boundaries=(1.0,), row_boundaries=(2.0,))
        with pytest.raises(AttributeError):
            grid.col_boundaries = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration: 106.pdf
# ---------------------------------------------------------------------------

PDF_PATH = Path(__file__).parent / "106.pdf"


@pytest.mark.skipif(not PDF_PATH.exists(), reason="106.pdf not present")
class TestIntegration106:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.geom = extract_geometry_from_path(str(PDF_PATH))
        self.grid = build_grid(self.geom)
        self.cells = assign_words_to_cells(self.geom, self.grid)

    def test_page_dimensions(self) -> None:
        assert self.geom.width == pytest.approx(842, abs=1)
        assert self.geom.height == pytest.approx(595, abs=1)

    def test_lines_detected(self) -> None:
        assert len(self.geom.lines) >= 30

    def test_words_detected(self) -> None:
        assert len(self.geom.words) >= 100

    def test_column_boundaries(self) -> None:
        # Left table: ~9 vertical lines, Right table: ~4 vertical lines = ~13 total
        assert len(self.grid.col_boundaries) >= 10

    def test_row_boundaries(self) -> None:
        assert len(self.grid.row_boundaries) >= 20

    def test_cells_non_empty(self) -> None:
        assert len(self.cells) >= 50

    def test_known_text_in_cells(self) -> None:
        """Check that known budget text appears somewhere in the extracted cells."""
        all_text = " ".join(c.text for c in self.cells)
        assert "会計管理費" in all_text
        assert "85,912" in all_text

    def test_overlay_produces_valid_pdf(self) -> None:
        pdf_bytes = read_pdf_bytes(str(PDF_PATH))
        result = render_overlay(pdf_bytes, self.geom, self.grid)
        # Valid PDF starts with %PDF
        assert result[:5] == b"%PDF-"
        assert len(result) > len(pdf_bytes)  # overlay adds content

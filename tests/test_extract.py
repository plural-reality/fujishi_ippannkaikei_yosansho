"""
Tests for budget_cell.extract + budget_cell.overlay — IO boundary integration tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_cell.extract import extract_geometry_from_path
from budget_cell.grid import build_grid
from budget_cell.cells import assign_words_to_cells
from budget_cell.overlay import read_pdf_bytes, render_overlay


PDF_PATH = Path(__file__).parent.parent / "106.pdf"


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
        assert len(self.grid.col_boundaries) >= 10

    def test_row_boundaries(self) -> None:
        assert len(self.grid.row_boundaries) >= 20

    def test_cells_non_empty(self) -> None:
        assert len(self.cells) >= 50

    def test_known_text_in_cells(self) -> None:
        all_text = " ".join(c.text for c in self.cells)
        assert "会計管理費" in all_text
        assert "85,912" in all_text

    def test_overlay_produces_valid_pdf(self) -> None:
        pdf_bytes = read_pdf_bytes(str(PDF_PATH))
        result = render_overlay(pdf_bytes, self.geom, self.grid)
        assert result[:5] == b"%PDF-"
        assert len(result) > len(pdf_bytes)

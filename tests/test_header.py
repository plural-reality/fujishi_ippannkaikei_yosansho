"""
Tests for budget_cell.header — page header (款/項) extraction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_cell.types import Grid, PageGeometry, Word, Line
from budget_cell.header import parse_page_header
from budget_cell.extract import extract_geometry_from_path
from budget_cell.grid import build_grid


# ---------------------------------------------------------------------------
# Unit tests with synthetic data
# ---------------------------------------------------------------------------

def _make_geom(above_words: tuple[Word, ...], table_words: tuple[Word, ...] = ()) -> PageGeometry:
    """Create a PageGeometry with words above and inside a table region."""
    return PageGeometry(
        width=600.0,
        height=800.0,
        lines=(
            Line(x0=50, y0=100, x1=50, y1=700, linewidth=1),   # vertical
            Line(x0=550, y0=100, x1=550, y1=700, linewidth=1), # vertical
            Line(x0=50, y0=100, x1=550, y1=100, linewidth=1),  # horizontal top
            Line(x0=50, y0=700, x1=550, y1=700, linewidth=1),  # horizontal bottom
        ),
        words=(*above_words, *table_words),
    )


class TestParsePageHeader:
    def test_basic_kan_kou(self) -> None:
        geom = _make_geom((
            Word(x0=50, y0=30, x1=80, y1=45, text="２款"),
            Word(x0=85, y0=30, x1=130, y1=45, text="総務費"),
            Word(x0=200, y0=30, x1=250, y1=45, text="１項"),
            Word(x0=255, y0=30, x1=340, y1=45, text="総務管理費"),
        ))
        grid = build_grid(geom)
        header = parse_page_header(geom, grid)
        assert header is not None
        assert header.kan_number == "２"
        assert header.kan_name == "総務費"
        assert header.kou_number == "１"
        assert header.kou_name == "総務管理費"

    def test_full_width_numbers(self) -> None:
        geom = _make_geom((
            Word(x0=50, y0=30, x1=100, y1=45, text="１０款"),
            Word(x0=105, y0=30, x1=150, y1=45, text="教育費"),
            Word(x0=200, y0=30, x1=250, y1=45, text="２項"),
            Word(x0=255, y0=30, x1=340, y1=45, text="小学校費"),
        ))
        grid = build_grid(geom)
        header = parse_page_header(geom, grid)
        assert header is not None
        assert header.kan_number == "１０"
        assert header.kan_name == "教育費"
        assert header.kou_number == "２"
        assert header.kou_name == "小学校費"

    def test_no_header_returns_none(self) -> None:
        """Pages without 款/項 (e.g. 給与費明細書) → None."""
        geom = _make_geom((
            Word(x0=50, y0=30, x1=200, y1=45, text="給与費明細書"),
        ))
        grid = build_grid(geom)
        assert parse_page_header(geom, grid) is None

    def test_no_words_above_grid(self) -> None:
        geom = _make_geom(())
        grid = build_grid(geom)
        assert parse_page_header(geom, grid) is None

    def test_split_token_kan_kou(self) -> None:
        geom = _make_geom((
            Word(x0=50, y0=30, x1=70, y1=45, text="２"),
            Word(x0=72, y0=30, x1=88, y1=45, text="款"),
            Word(x0=90, y0=30, x1=140, y1=45, text="総務費"),
            Word(x0=200, y0=30, x1=220, y1=45, text="１"),
            Word(x0=222, y0=30, x1=236, y1=45, text="項"),
            Word(x0=238, y0=30, x1=330, y1=45, text="総務管理費"),
        ))
        grid = build_grid(geom)
        header = parse_page_header(geom, grid)
        assert header is not None
        assert header.kan_number == "２"
        assert header.kou_number == "１"


# ---------------------------------------------------------------------------
# Integration: 106.pdf
# ---------------------------------------------------------------------------

PDF_PATH = Path(__file__).parent.parent / "106.pdf"


@pytest.mark.skipif(not PDF_PATH.exists(), reason="106.pdf not present")
class TestIntegration106:
    def test_parses_header(self) -> None:
        geom = extract_geometry_from_path(str(PDF_PATH))
        grid = build_grid(geom)
        header = parse_page_header(geom, grid)
        assert header is not None
        assert header.kan_name != ""
        assert header.kou_name != ""

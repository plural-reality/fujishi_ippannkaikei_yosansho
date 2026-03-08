"""
Tests for budget_cell.types — immutability guarantees.
"""

from __future__ import annotations

import pytest

from budget_cell.types import (
    Cell,
    FlatRow,
    Grid,
    Line,
    MokuRecord,
    PageBudget,
    SetsumeiEntry,
    Word,
    Zaigen,
)


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

    def test_setsumei_frozen(self) -> None:
        e = SetsumeiEntry("coded", "001", "test", 100)
        with pytest.raises(AttributeError):
            e.name = "x"  # type: ignore[misc]

    def test_moku_frozen(self) -> None:
        m = MokuRecord("x", 1, 2, 3, Zaigen(None, None, None, None), ())
        with pytest.raises(AttributeError):
            m.name = "y"  # type: ignore[misc]

    def test_page_budget_frozen(self) -> None:
        p = PageBudget((), ())
        with pytest.raises(AttributeError):
            p.moku_records = ()  # type: ignore[misc]

    def test_flat_row_frozen(self) -> None:
        r = FlatRow(
            moku_name="", honendo=None, zenendo=None, hikaku=None,
            kokuken=None, chihousei=None, sonota=None, ippan=None,
            setsu_number=None, setsu_name="", setsu_amount=None,
            sub_item_name="", sub_item_amount=None,
            setsumei_code="", setsumei_name="", setsumei_amount=None,
            is_orphan=False,
        )
        with pytest.raises(AttributeError):
            r.moku_name = "x"  # type: ignore[misc]

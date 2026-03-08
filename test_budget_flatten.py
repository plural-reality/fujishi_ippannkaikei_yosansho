"""
Tests for budget_flatten — pure flatten transforms.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_parse import (
    MokuRecord,
    PageBudget,
    SetsuRecord,
    SetsumeiEntry,
    Zaigen,
    parse_page_budget,
)
from pdf_cell_detect import assign_words_to_cells, build_grid, extract_geometry_from_path
from budget_flatten import (
    HEADERS,
    FlatRow,
    flatten_moku,
    flatten_orphans,
    flatten_page_budget,
    flatten_setsu,
    row_to_tuple,
    to_table,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ZAIGEN = Zaigen(kokuken=100, chihousei=None, sonota=200, ippan=300)

SAMPLE_SETSUMEI = (
    SetsumeiEntry("coded", "001", "給与費", 998),
    SetsumeiEntry("text", None, "（定数外）", None),
)

SAMPLE_SETSU = SetsuRecord(
    number=1, name="報酬", amount=829,
    sub_items=(("費用弁償", 42),),
    setsumei=SAMPLE_SETSUMEI,
)

SAMPLE_SETSU_EMPTY = SetsuRecord(
    number=24, name="積立金", amount=1510,
    sub_items=(), setsumei=(),
)

SAMPLE_MOKU = MokuRecord(
    name="11 会計管理費",
    honendo=85912, zenendo=87506, hikaku=-1594,
    zaigen=SAMPLE_ZAIGEN,
    setsu_list=(SAMPLE_SETSU, SAMPLE_SETSU_EMPTY),
)


# ---------------------------------------------------------------------------
# flatten_setsu
# ---------------------------------------------------------------------------

class TestFlattenSetsu:
    def test_produces_rows_for_sub_items_and_setsumei(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        # 1 sub-item + 2 setsumei = 3 rows
        assert len(rows) == 3

    def test_sub_item_row_content(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        sub_row = rows[0]
        assert sub_row.sub_item_name == "費用弁償"
        assert sub_row.sub_item_amount == 42
        assert sub_row.setsu_name == "報酬"
        assert sub_row.moku_name == "11 会計管理費"

    def test_setsumei_row_content(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        coded_row = rows[1]
        assert coded_row.setsumei_code == "001"
        assert coded_row.setsumei_name == "給与費"
        assert coded_row.setsumei_amount == 998

    def test_empty_setsu_produces_one_row(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU_EMPTY)
        assert len(rows) == 1
        assert rows[0].setsu_name == "積立金"
        assert rows[0].setsu_amount == 1510

    def test_orphan_setsu(self) -> None:
        rows = flatten_setsu(None, SAMPLE_SETSU, is_orphan=True)
        assert all(r.is_orphan for r in rows)
        assert all(r.moku_name == "" for r in rows)
        assert all(r.honendo is None for r in rows)

    def test_all_rows_frozen(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        for r in rows:
            with pytest.raises(AttributeError):
                r.moku_name = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# flatten_moku
# ---------------------------------------------------------------------------

class TestFlattenMoku:
    def test_flattens_all_setsu(self) -> None:
        rows = flatten_moku(SAMPLE_MOKU)
        # SAMPLE_SETSU: 3 rows, SAMPLE_SETSU_EMPTY: 1 row
        assert len(rows) == 4

    def test_all_rows_carry_moku_context(self) -> None:
        rows = flatten_moku(SAMPLE_MOKU)
        assert all(r.moku_name == "11 会計管理費" for r in rows)
        assert all(r.honendo == 85912 for r in rows)

    def test_not_orphan(self) -> None:
        rows = flatten_moku(SAMPLE_MOKU)
        assert all(not r.is_orphan for r in rows)


# ---------------------------------------------------------------------------
# flatten_orphans
# ---------------------------------------------------------------------------

class TestFlattenOrphans:
    def test_basic(self) -> None:
        rows = flatten_orphans((SAMPLE_SETSU,))
        assert len(rows) == 3
        assert all(r.is_orphan for r in rows)

    def test_empty(self) -> None:
        assert flatten_orphans(()) == ()


# ---------------------------------------------------------------------------
# flatten_page_budget
# ---------------------------------------------------------------------------

class TestFlattenPageBudget:
    def test_combines_orphans_and_moku(self) -> None:
        budget = PageBudget(
            moku_records=(SAMPLE_MOKU,),
            orphan_setsu=(SAMPLE_SETSU_EMPTY,),
        )
        rows = flatten_page_budget(budget)
        # orphan: 1, moku: 4
        assert len(rows) == 5
        # Orphans come first
        assert rows[0].is_orphan
        assert not rows[-1].is_orphan

    def test_empty_budget(self) -> None:
        budget = PageBudget(moku_records=(), orphan_setsu=())
        assert flatten_page_budget(budget) == ()


# ---------------------------------------------------------------------------
# row_to_tuple / to_table
# ---------------------------------------------------------------------------

class TestRowToTuple:
    def test_length_matches_headers(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        for r in rows:
            assert len(row_to_tuple(r)) == len(HEADERS)

    def test_none_replaced_with_empty(self) -> None:
        row = flatten_setsu(None, SAMPLE_SETSU_EMPTY, is_orphan=True)[0]
        t = row_to_tuple(row)
        # honendo is None → ""
        assert t[1] == ""


class TestToTable:
    def test_first_row_is_headers(self) -> None:
        budget = PageBudget(moku_records=(SAMPLE_MOKU,), orphan_setsu=())
        table = to_table(budget)
        assert table[0] == HEADERS

    def test_data_rows_follow(self) -> None:
        budget = PageBudget(moku_records=(SAMPLE_MOKU,), orphan_setsu=())
        table = to_table(budget)
        assert len(table) == 5  # 1 header + 4 data rows


# ---------------------------------------------------------------------------
# Integration: 106.pdf
# ---------------------------------------------------------------------------

PDF_PATH = Path(__file__).parent / "106.pdf"


@pytest.mark.skipif(not PDF_PATH.exists(), reason="106.pdf not present")
class TestIntegration106:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        geom = extract_geometry_from_path(str(PDF_PATH))
        grid = build_grid(geom)
        cells = assign_words_to_cells(geom, grid)
        self.budget = parse_page_budget(cells)
        self.flat = flatten_page_budget(self.budget)
        self.table = to_table(self.budget)

    def test_has_rows(self) -> None:
        assert len(self.flat) >= 10

    def test_moku_context_propagated(self) -> None:
        moku_rows = [r for r in self.flat if not r.is_orphan]
        assert all("会計管理費" in r.moku_name for r in moku_rows)

    def test_orphan_rows_present(self) -> None:
        orphan_rows = [r for r in self.flat if r.is_orphan]
        assert len(orphan_rows) >= 1

    def test_known_setsumei(self) -> None:
        coded = [r for r in self.flat if r.setsumei_code == "001" and "給与費" in r.setsumei_name]
        assert len(coded) >= 1
        assert coded[0].setsumei_amount == 998

    def test_table_header(self) -> None:
        assert self.table[0] == HEADERS

    def test_table_printable(self) -> None:
        # Every cell should be str or int (no None)
        for row in self.table[1:]:
            assert all(not (v is None) for v in row)

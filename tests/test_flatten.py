"""
Tests for budget_cell.flatten — pure flatten transforms + generic ffill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_cell.types import (
    FlatRow,
    MokuRecord,
    PageBudget,
    PageHeader,
    SetsuRecord,
    SetsumeiEntry,
    Zaigen,
)
from budget_cell.extract import extract_geometry_from_path
from budget_cell.grid import build_grid
from budget_cell.cells import assign_words_to_cells
from budget_cell.parse import parse_page_budget
from budget_cell.flatten import (
    HEADERS,
    KAN_KOU_FIELDS,
    MOKU_FIELDS,
    ffill,
    flatten_moku,
    flatten_orphans,
    flatten_page_budget,
    flatten_setsu,
    row_to_tuple,
    sectioned_ffill,
    stamp_page,
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

SAMPLE_HEADER = PageHeader(
    kan_number="２", kan_name="総務費",
    kou_number="１", kou_name="総務管理費",
)

def _empty_row(**overrides) -> FlatRow:
    defaults = dict(
        kan_name="", kou_name="",
        moku_name="", honendo=None, zenendo=None, hikaku=None,
        kokuken=None, chihousei=None, sonota=None, ippan=None,
        setsu_number=None, setsu_name="", setsu_amount=None,
        sub_item_name="", sub_item_amount=None,
        setsumei_code="", setsumei_name="", setsumei_amount=None,
    )
    return FlatRow(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# flatten_setsu
# ---------------------------------------------------------------------------

class TestFlattenSetsu:
    def test_produces_rows_for_sub_items_and_setsumei(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
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

    def test_orphan_setsu_has_empty_moku(self) -> None:
        rows = flatten_setsu(None, SAMPLE_SETSU)
        assert all(r.moku_name == "" for r in rows)
        assert all(r.honendo is None for r in rows)

    def test_kan_kou_always_empty(self) -> None:
        """flatten produces empty kan/kou — stamping is a separate step."""
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        assert all(r.kan_name == "" for r in rows)
        assert all(r.kou_name == "" for r in rows)

    def test_all_rows_frozen(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        for r in rows:
            with pytest.raises(AttributeError):
                r.moku_name = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# flatten_moku / flatten_orphans / flatten_page_budget
# ---------------------------------------------------------------------------

class TestFlattenMoku:
    def test_flattens_all_setsu(self) -> None:
        rows = flatten_moku(SAMPLE_MOKU)
        assert len(rows) == 4

    def test_all_rows_carry_moku_context(self) -> None:
        rows = flatten_moku(SAMPLE_MOKU)
        assert all(r.moku_name == "11 会計管理費" for r in rows)
        assert all(r.honendo == 85912 for r in rows)


class TestFlattenOrphans:
    def test_basic(self) -> None:
        rows = flatten_orphans((SAMPLE_SETSU,))
        assert len(rows) == 3
        assert all(r.moku_name == "" for r in rows)

    def test_empty(self) -> None:
        assert flatten_orphans(()) == ()


class TestFlattenPageBudget:
    def test_combines_orphans_and_moku(self) -> None:
        budget = PageBudget(
            moku_records=(SAMPLE_MOKU,),
            orphan_setsu=(SAMPLE_SETSU_EMPTY,),
        )
        rows = flatten_page_budget(budget)
        assert len(rows) == 5
        assert rows[0].moku_name == ""
        assert rows[-1].moku_name == "11 会計管理費"

    def test_empty_budget(self) -> None:
        budget = PageBudget(moku_records=(), orphan_setsu=())
        assert flatten_page_budget(budget) == ()


# ---------------------------------------------------------------------------
# stamp_page
# ---------------------------------------------------------------------------

class TestStampPage:
    def test_stamps_first_row_only(self) -> None:
        rows = flatten_moku(SAMPLE_MOKU)
        stamped = stamp_page(SAMPLE_HEADER, rows)
        assert stamped[0].kan_name == "総務費"
        assert stamped[0].kou_name == "総務管理費"
        assert all(r.kan_name == "" for r in stamped[1:])

    def test_empty_rows(self) -> None:
        assert stamp_page(SAMPLE_HEADER, ()) == ()


# ---------------------------------------------------------------------------
# ffill
# ---------------------------------------------------------------------------

class TestFfill:
    def test_fills_empty_from_above(self) -> None:
        row_with = _empty_row(moku_name="目A", honendo=100, zenendo=200)
        row_empty = _empty_row(setsu_number=2, setsu_name="旅費", setsu_amount=30)
        filled = ffill((row_with, row_empty), MOKU_FIELDS)
        assert filled[1].moku_name == "目A"
        assert filled[1].honendo == 100

    def test_does_not_fill_non_specified_fields(self) -> None:
        row_with = _empty_row(moku_name="目A", setsumei_code="001")
        row_empty = _empty_row()
        filled = ffill((row_with, row_empty), MOKU_FIELDS)
        assert filled[1].setsumei_code == ""

    def test_empty_input(self) -> None:
        assert ffill((), MOKU_FIELDS) == ()

    def test_chains_through_multiple_empty_rows(self) -> None:
        base = _empty_row(moku_name="目B", honendo=500)
        empty = _empty_row()
        filled = ffill((base, empty, empty, empty), MOKU_FIELDS)
        assert all(r.moku_name == "目B" for r in filled)


# ---------------------------------------------------------------------------
# sectioned_ffill
# ---------------------------------------------------------------------------

class TestSectionedFfill:
    def test_does_not_leak_across_sections(self) -> None:
        """moku from section A must not bleed into section B."""
        sec_a_row = _empty_row(kan_name="A款", kou_name="A項", moku_name="目1", honendo=100)
        sec_b_row = _empty_row(kan_name="B款", kou_name="B項", setsu_number=1, setsu_name="報酬")
        filled = sectioned_ffill(
            (sec_a_row, sec_b_row),
            MOKU_FIELDS,
            section_key=KAN_KOU_FIELDS,
        )
        assert filled[0].moku_name == "目1"
        assert filled[1].moku_name == ""  # NOT "目1"

    def test_fills_within_section(self) -> None:
        row1 = _empty_row(kan_name="A款", kou_name="A項", moku_name="目1", honendo=100)
        row2 = _empty_row(kan_name="A款", kou_name="A項")
        filled = sectioned_ffill(
            (row1, row2),
            MOKU_FIELDS,
            section_key=KAN_KOU_FIELDS,
        )
        assert filled[1].moku_name == "目1"
        assert filled[1].honendo == 100


# ---------------------------------------------------------------------------
# row_to_tuple / to_table
# ---------------------------------------------------------------------------

class TestRowToTuple:
    def test_length_matches_headers(self) -> None:
        rows = flatten_setsu(SAMPLE_MOKU, SAMPLE_SETSU)
        for r in rows:
            assert len(row_to_tuple(r)) == len(HEADERS)

    def test_none_replaced_with_empty(self) -> None:
        row = flatten_setsu(None, SAMPLE_SETSU_EMPTY)[0]
        t = row_to_tuple(row)
        # honendo (index 3) should be "" not None
        assert t[3] == ""


class TestToTable:
    def test_first_row_is_headers(self) -> None:
        budget = PageBudget(moku_records=(SAMPLE_MOKU,), orphan_setsu=())
        table = to_table(budget)
        assert table[0] == HEADERS

    def test_data_rows_follow(self) -> None:
        budget = PageBudget(moku_records=(SAMPLE_MOKU,), orphan_setsu=())
        table = to_table(budget)
        assert len(table) == 5


# ---------------------------------------------------------------------------
# Integration: 106.pdf
# ---------------------------------------------------------------------------

PDF_PATH = Path(__file__).parent.parent / "106.pdf"


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

    def test_moku_rows_have_context(self) -> None:
        moku_rows = [r for r in self.flat if r.moku_name != ""]
        assert all("会計管理費" in r.moku_name for r in moku_rows)

    def test_orphan_rows_have_empty_moku(self) -> None:
        orphan_rows = [r for r in self.flat if r.moku_name == ""]
        assert len(orphan_rows) >= 1

    def test_known_setsumei(self) -> None:
        coded = [r for r in self.flat if r.setsumei_code == "001" and "給与費" in r.setsumei_name]
        assert len(coded) >= 1
        assert coded[0].setsumei_amount == 998

    def test_table_header(self) -> None:
        assert self.table[0] == HEADERS

    def test_table_printable(self) -> None:
        for row in self.table[1:]:
            assert all(not (v is None) for v in row)

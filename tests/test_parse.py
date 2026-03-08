"""
Tests for budget_cell.parse — budget table parsing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_cell.types import Cell, SetsumeiEntry, Word
from budget_cell.extract import extract_geometry_from_path
from budget_cell.grid import build_grid
from budget_cell.cells import assign_words_to_cells
from budget_cell.parse import (
    CellIndex,
    build_cell_index,
    build_moku_record,
    build_setsu_record,
    classify_all_rows,
    classify_row,
    collect_full_name,
    detect_header_rows,
    group_rows_by_moku,
    group_rows_by_setsu,
    is_header_row,
    parse_setsumei_cell_lines,
    parse_setsumei_cells,
    parse_amount,
    parse_page_budget,
    parse_setsumei_cell,
    parse_setsu_text,
    split_words_into_lines,
    text_at,
)


# ---------------------------------------------------------------------------
# parse_amount
# ---------------------------------------------------------------------------

class TestParseAmount:
    def test_plain_number(self) -> None:
        assert parse_amount("85,912") == 85912

    def test_negative_triangle(self) -> None:
        assert parse_amount("△1,594") == -1594

    def test_negative_minus(self) -> None:
        assert parse_amount("-500") == -500

    def test_no_comma(self) -> None:
        assert parse_amount("42") == 42

    def test_empty(self) -> None:
        assert parse_amount("") is None

    def test_whitespace(self) -> None:
        assert parse_amount("  ") is None

    def test_large_number(self) -> None:
        assert parse_amount("9,616,154") == 9616154


# ---------------------------------------------------------------------------
# parse_setsu_text
# ---------------------------------------------------------------------------

class TestParseSetsuText:
    def test_basic(self) -> None:
        assert parse_setsu_text("10 需用費") == (10, "需用費")

    def test_single_digit(self) -> None:
        assert parse_setsu_text("1 報酬") == (1, "報酬")

    def test_two_digit(self) -> None:
        assert parse_setsu_text("24 積立金") == (24, "積立金")

    def test_with_punctuation(self) -> None:
        assert parse_setsu_text("18 負担金、補助") == (18, "負担金、補助")

    def test_not_setsu(self) -> None:
        assert parse_setsu_text("消耗品費") is None

    def test_empty(self) -> None:
        assert parse_setsu_text("") is None

    def test_continuation_text(self) -> None:
        assert parse_setsu_text("及び交付金") is None


# ---------------------------------------------------------------------------
# parse_setsumei_cell
# ---------------------------------------------------------------------------

class TestParseSetsumeiCell:
    """Test coordinate-based setsumei parsing.

    Cell layout: x0=0, x1=100.
    Code threshold: w.x0 - cell.x0 < 25 (i.e., w.x0 < 25).
    Amount threshold: cell.x1 - w.x1 < 50 (i.e., w.x1 > 50).
    """

    def test_coded_with_amount(self) -> None:
        # "001 財政事務費 2,498"
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="001 財政事務費 2,498",
                    words=(
                        Word(x0=5, y0=2, x1=20, y1=8, text="001"),
                        Word(x0=25, y0=2, x1=48, y1=8, text="財政事務費"),
                        Word(x0=70, y0=2, x1=95, y1=8, text="2,498"),
                    ))
        result = parse_setsumei_cell(cell)
        assert result == SetsumeiEntry("coded", "001", "財政事務費", 2498)

    def test_coded_without_amount(self) -> None:
        # "001 パートタイム会計年度任用職員"
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="001 パートタイム会計年度任用職員",
                    words=(
                        Word(x0=5, y0=2, x1=20, y1=8, text="001"),
                        Word(x0=25, y0=2, x1=48, y1=8, text="パートタイム会計年度任用職員"),
                    ))
        result = parse_setsumei_cell(cell)
        assert result == SetsumeiEntry("coded", "001", "パートタイム会計年度任用職員", None)

    def test_text_with_amount(self) -> None:
        # "地方財務協会賛助会費 40"
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="地方財務協会賛助会費 40",
                    words=(
                        Word(x0=25, y0=2, x1=48, y1=8, text="地方財務協会賛助会費"),
                        Word(x0=80, y0=2, x1=92, y1=8, text="40"),
                    ))
        result = parse_setsumei_cell(cell)
        assert result == SetsumeiEntry("text", None, "地方財務協会賛助会費", 40)

    def test_plain_text(self) -> None:
        # "統一的な基準による財務書類整備"
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="統一的な基準による財務書類整備",
                    words=(
                        Word(x0=25, y0=2, x1=48, y1=8, text="統一的な基準による財務書類整備"),
                    ))
        result = parse_setsumei_cell(cell)
        assert result == SetsumeiEntry("text", None, "統一的な基準による財務書類整備", None)

    def test_parenthetical(self) -> None:
        # "（定数外）"
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="（定数外）",
                    words=(
                        Word(x0=30, y0=2, x1=48, y1=8, text="（定数外）"),
                    ))
        result = parse_setsumei_cell(cell)
        assert result == SetsumeiEntry("text", None, "（定数外）", None)

    def test_text_with_number_suffix(self) -> None:
        # "事務補助 1人" — neither word is near right edge or 3-digit code
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="事務補助 1人",
                    words=(
                        Word(x0=30, y0=2, x1=45, y1=8, text="事務補助"),
                        Word(x0=46, y0=2, x1=49, y1=8, text="1人"),
                    ))
        result = parse_setsumei_cell(cell)
        assert result.kind == "text"
        assert "事務補助" in result.name

    def test_empty_cell(self) -> None:
        cell = Cell(row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                    text="", words=())
        result = parse_setsumei_cell(cell)
        assert result == SetsumeiEntry("text", None, "", None)


class TestSetsumeiLineSplitAndFold:
    def test_split_words_into_lines_by_y(self) -> None:
        words = (
            Word(x0=30, y0=10.0, x1=45, y1=12.0, text="A"),
            Word(x0=50, y0=10.1, x1=60, y1=12.1, text="B"),
            Word(x0=30, y0=18.0, x1=45, y1=20.0, text="C"),
        )
        lines = split_words_into_lines(words)
        assert len(lines) == 2
        assert tuple(w.text for w in lines[0]) == ("A", "B")
        assert tuple(w.text for w in lines[1]) == ("C",)

    def test_parse_setsumei_cell_lines_multiple_amount_lines(self) -> None:
        cell = Cell(
            row=0, col=11, x0=0, y0=0, x1=100, y1=20,
            text="001 給与費 998 001 パートタイム会計年度任用職員 998",
            words=(
                Word(x0=5, y0=2, x1=20, y1=8, text="001"),
                Word(x0=25, y0=2, x1=48, y1=8, text="給与費"),
                Word(x0=80, y0=2, x1=95, y1=8, text="998"),
                Word(x0=5, y0=12, x1=20, y1=18, text="001"),
                Word(x0=25, y0=12, x1=70, y1=18, text="パートタイム会計年度任用職員"),
                Word(x0=80, y0=12, x1=95, y1=18, text="998"),
            ),
        )
        lines = parse_setsumei_cell_lines(cell)
        assert len(lines) == 2
        assert lines[0][1] is True
        assert lines[0][0] == SetsumeiEntry("coded", "001", "給与費", 998)
        assert lines[1][1] is True
        assert lines[1][0] == SetsumeiEntry("coded", "001", "パートタイム会計年度任用職員", 998)

    def test_parse_setsumei_cells_attach_non_amount_line_to_previous(self) -> None:
        cells = (
            Cell(
                row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                text="001 給与費 998",
                words=(
                    Word(x0=5, y0=2, x1=20, y1=8, text="001"),
                    Word(x0=25, y0=2, x1=48, y1=8, text="給与費"),
                    Word(x0=80, y0=2, x1=95, y1=8, text="998"),
                ),
            ),
            Cell(
                row=1, col=11, x0=0, y0=10, x1=100, y1=20,
                text="パートタイム会計年度任用職員",
                words=(
                    Word(x0=25, y0=12, x1=70, y1=18, text="パートタイム会計年度任用職員"),
                ),
            ),
        )
        entries = parse_setsumei_cells(cells)
        assert entries == (
            SetsumeiEntry("coded", "001", "給与費", 998, "パートタイム会計年度任用職員"),
        )

    def test_parse_setsumei_cells_no_base_keeps_text_row(self) -> None:
        cells = (
            Cell(
                row=0, col=11, x0=0, y0=0, x1=100, y1=10,
                text="（定数外）",
                words=(Word(x0=30, y0=2, x1=48, y1=8, text="（定数外）"),),
            ),
        )
        entries = parse_setsumei_cells(cells)
        assert entries == (SetsumeiEntry("text", None, "（定数外）", None),)

    def test_parse_setsumei_cells_keeps_indent_for_child_amount_lines(self) -> None:
        cell = Cell(
            row=0, col=11, x0=0, y0=0, x1=100, y1=24,
            text="002 親 1,510 001 子 1,510",
            words=(
                Word(x0=5, y0=2, x1=20, y1=8, text="002"),
                Word(x0=25, y0=2, x1=40, y1=8, text="親"),
                Word(x0=82, y0=2, x1=95, y1=8, text="1,510"),
                Word(x0=12, y0=14, x1=27, y1=20, text="001"),
                Word(x0=32, y0=14, x1=45, y1=20, text="子"),
                Word(x0=82, y0=14, x1=95, y1=20, text="1,510"),
            ),
        )
        entries = parse_setsumei_cells((cell,))
        assert entries[0] == SetsumeiEntry("coded", "002", "親", 1510)
        assert entries[1].code == "001"
        assert entries[1].amount == 1510
        assert entries[1].name.startswith("  ")
        assert entries[1].name.strip() == "子"


# ---------------------------------------------------------------------------
# build_cell_index / text_at
# ---------------------------------------------------------------------------

SAMPLE_CELLS = (
    Cell(row=0, col=0, x0=0, y0=0, x1=10, y1=10, text="目", words=()),
    Cell(row=0, col=1, x0=10, y0=0, x1=20, y1=10, text="千円", words=()),
    Cell(row=1, col=0, x0=0, y0=10, x1=10, y1=20, text="11 会計管理費", words=()),
    Cell(row=1, col=1, x0=10, y0=10, x1=20, y1=20, text="85,912", words=()),
    Cell(row=1, col=9, x0=50, y0=10, x1=60, y1=20, text="1 報酬", words=()),
    Cell(row=1, col=10, x0=60, y0=10, x1=70, y1=20, text="829", words=()),
    Cell(row=1, col=11, x0=70, y0=10, x1=100, y1=20, text="001 給与費 998",
         words=(
             Word(x0=72, y0=12, x1=80, y1=18, text="001"),
             Word(x0=82, y0=12, x1=90, y1=18, text="給与費"),
             Word(x0=92, y0=12, x1=98, y1=18, text="998"),
         )),
    Cell(row=2, col=9, x0=50, y0=20, x1=60, y1=30, text="4 共済費", words=()),
    Cell(row=2, col=10, x0=60, y0=20, x1=70, y1=30, text="127", words=()),
    Cell(row=3, col=11, x0=70, y0=30, x1=100, y1=40, text="（定数外）",
         words=(
             Word(x0=80, y0=32, x1=90, y1=38, text="（定数外）"),
         )),
    Cell(row=4, col=11, x0=70, y0=40, x1=100, y1=50, text="事務補助 1人",
         words=(
             Word(x0=80, y0=42, x1=88, y1=48, text="事務補助"),
             Word(x0=89, y0=42, x1=94, y1=48, text="1人"),
         )),
)


class TestCellIndex:
    def test_build_and_lookup(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert text_at(idx, 0, 0) == "目"
        assert text_at(idx, 1, 1) == "85,912"

    def test_missing(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert text_at(idx, 99, 99) is None


# ---------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------

class TestHeaderDetection:
    def test_header_row_detected(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert is_header_row(idx, 0) is True

    def test_data_row_not_header(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert is_header_row(idx, 1) is False

    def test_detect_header_rows(self) -> None:
        headers = detect_header_rows(SAMPLE_CELLS)
        assert 0 in headers
        assert 1 not in headers


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------

class TestClassifyRow:
    def test_header(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert classify_row(idx, 0, frozenset({0})) == "header"

    def test_moku(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert classify_row(idx, 1, frozenset({0})) == "moku"

    def test_setsu(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert classify_row(idx, 2, frozenset({0})) == "setsu"

    def test_setsumei(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        assert classify_row(idx, 3, frozenset({0})) == "setsumei"

    def test_classify_all(self) -> None:
        result = classify_all_rows(SAMPLE_CELLS)
        kinds = {r: k for r, k in result}
        assert kinds[0] == "header"
        assert kinds[1] == "moku"
        assert kinds[2] == "setsu"
        assert kinds[3] == "setsumei"


# ---------------------------------------------------------------------------
# Continuation detection
# ---------------------------------------------------------------------------

CONTINUATION_CELLS = (
    Cell(row=0, col=9, x0=50, y0=0, x1=60, y1=10, text="18 負担金、補助", words=()),
    Cell(row=0, col=10, x0=60, y0=0, x1=70, y1=10, text="71", words=()),
    Cell(row=1, col=9, x0=50, y0=10, x1=60, y1=20, text="及び交付金", words=()),
    Cell(row=2, col=9, x0=50, y0=20, x1=60, y1=30, text="負担金", words=()),
    Cell(row=2, col=10, x0=60, y0=20, x1=70, y1=30, text="71", words=()),
)


class TestContinuation:
    def test_continuation_detected(self) -> None:
        idx = build_cell_index(CONTINUATION_CELLS)
        assert classify_row(idx, 1, frozenset()) == "continuation"

    def test_collect_full_name(self) -> None:
        idx = build_cell_index(CONTINUATION_CELLS)
        full = collect_full_name(idx, 0, (1, 2))
        assert full == "18 負担金、補助及び交付金"

    def test_collect_stops_at_non_continuation(self) -> None:
        idx = build_cell_index(CONTINUATION_CELLS)
        full = collect_full_name(idx, 0, (1, 2))
        assert "負担金負担金" not in full


# ---------------------------------------------------------------------------
# group_rows_by_moku
# ---------------------------------------------------------------------------

class TestGroupByMoku:
    def test_single_moku(self) -> None:
        classified = (
            (0, "header"), (1, "moku"), (2, "setsu"), (3, "setsumei"),
        )
        groups = group_rows_by_moku(classified)
        assert len(groups) == 1
        assert groups[0] == (1, (2, 3))

    def test_orphan_before_moku(self) -> None:
        classified = (
            (0, "header"), (1, "setsu"), (2, "setsumei"),
            (3, "moku"), (4, "setsu"),
        )
        groups = group_rows_by_moku(classified)
        assert len(groups) == 2
        assert groups[0][0] is None
        assert groups[0][1] == (1, 2)
        assert groups[1][0] == 3
        assert groups[1][1] == (4,)

    def test_multiple_moku(self) -> None:
        classified = (
            (0, "moku"), (1, "setsu"),
            (2, "moku"), (3, "setsu"), (4, "setsumei"),
        )
        groups = group_rows_by_moku(classified)
        assert len(groups) == 2
        assert groups[0] == (0, (1,))
        assert groups[1] == (2, (3, 4))

    def test_empty(self) -> None:
        assert group_rows_by_moku(()) == ()


# ---------------------------------------------------------------------------
# group_rows_by_setsu
# ---------------------------------------------------------------------------

class TestGroupBySetsu:
    def test_basic(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        groups = group_rows_by_setsu(idx, (1, 2, 3, 4))
        assert len(groups) == 2
        assert groups[0][0] == 1
        assert groups[1][0] == 2
        assert 3 in groups[1][1]
        assert 4 in groups[1][1]

    def test_orphan_before_setsu(self) -> None:
        cells = (
            Cell(row=0, col=11, x0=70, y0=0, x1=100, y1=10, text="some text",
                 words=(Word(x0=80, y0=2, x1=90, y1=8, text="some text"),)),
            Cell(row=1, col=9, x0=50, y0=10, x1=60, y1=20, text="1 報酬", words=()),
            Cell(row=1, col=10, x0=60, y0=10, x1=70, y1=20, text="100", words=()),
        )
        idx = build_cell_index(cells)
        groups = group_rows_by_setsu(idx, (0, 1))
        assert len(groups) == 2
        assert groups[0][0] is None
        assert groups[0][1] == (0,)
        assert groups[1][0] == 1

    def test_empty(self) -> None:
        idx = build_cell_index(())
        assert group_rows_by_setsu(idx, ()) == ()


# ---------------------------------------------------------------------------
# build_setsu_record
# ---------------------------------------------------------------------------

class TestBuildSetsuRecord:
    def test_basic_setsu(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        record = build_setsu_record(idx, 2, (3, 4))
        assert record.number == 4
        assert record.name == "共済費"
        assert record.amount == 127
        assert len(record.setsumei) == 1
        assert record.setsumei[0].name == "（定数外）"
        assert record.setsumei[0].supplement == "事務補助 1人"

    def test_setsu_with_continuation(self) -> None:
        idx = build_cell_index(CONTINUATION_CELLS)
        record = build_setsu_record(idx, 0, (1, 2))
        assert record.number == 18
        assert record.name == "負担金、補助及び交付金"
        assert record.amount == 71
        assert len(record.sub_items) == 1
        assert record.sub_items[0] == ("負担金", 71)

    def test_orphan_setsu(self) -> None:
        cells = (
            Cell(row=0, col=11, x0=70, y0=0, x1=100, y1=10, text="some description",
                 words=(Word(x0=80, y0=2, x1=90, y1=8, text="some description"),)),
        )
        idx = build_cell_index(cells)
        record = build_setsu_record(idx, None, (0,))
        assert record.number is None
        assert record.name == ""
        assert len(record.setsumei) == 1


# ---------------------------------------------------------------------------
# build_moku_record
# ---------------------------------------------------------------------------

class TestBuildMokuRecord:
    def test_from_sample(self) -> None:
        idx = build_cell_index(SAMPLE_CELLS)
        record = build_moku_record(idx, 1, (2, 3, 4))
        assert record.name == "11 会計管理費"
        assert record.honendo == 85912
        assert len(record.setsu_list) >= 2
        assert record.setsu_list[0].number == 1
        assert record.setsu_list[0].name == "報酬"
        assert record.setsu_list[1].number == 4
        assert record.setsu_list[1].name == "共済費"


# ---------------------------------------------------------------------------
# parse_page_budget
# ---------------------------------------------------------------------------

class TestParsePageBudget:
    def test_from_sample(self) -> None:
        budget = parse_page_budget(SAMPLE_CELLS)
        assert len(budget.moku_records) == 1
        assert budget.moku_records[0].name == "11 会計管理費"
        assert budget.moku_records[0].honendo == 85912

    def test_empty(self) -> None:
        budget = parse_page_budget(())
        assert budget.moku_records == ()
        assert budget.orphan_setsu == ()


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
        self.cells = assign_words_to_cells(geom, grid)
        self.budget = parse_page_budget(self.cells)

    def test_has_one_moku(self) -> None:
        assert len(self.budget.moku_records) == 1

    def test_moku_name(self) -> None:
        assert "会計管理費" in self.budget.moku_records[0].name

    def test_moku_amounts(self) -> None:
        moku = self.budget.moku_records[0]
        assert moku.honendo == 85912
        assert moku.zenendo == 87506
        assert moku.hikaku == -1594

    def test_zaigen(self) -> None:
        z = self.budget.moku_records[0].zaigen
        assert z.kokuken == 576
        assert z.sonota == 1501
        assert z.ippan == 83835

    def test_has_setsu(self) -> None:
        moku = self.budget.moku_records[0]
        assert len(moku.setsu_list) >= 3
        names = {s.name for s in moku.setsu_list}
        assert "報酬" in names
        assert "共済費" in names
        assert "旅費" in names

    def test_setsu_amounts(self) -> None:
        moku = self.budget.moku_records[0]
        houshuu = next(s for s in moku.setsu_list if s.name == "報酬")
        assert houshuu.amount == 829
        assert houshuu.number == 1

    def test_setsu_setsumei(self) -> None:
        moku = self.budget.moku_records[0]
        houshuu = next(s for s in moku.setsu_list if s.name == "報酬")
        coded = [e for e in houshuu.setsumei if e.kind == "coded"]
        assert any(e.code == "001" and e.name == "給与費" and e.amount == 998 for e in coded)
        assert any(e.code == "001" and "パートタイム会計年度任用職員" in e.name and e.amount == 998 for e in coded)
        assert all(e.amount != 998998 for e in coded if e.amount is not None)

    def test_orphan_setsu_exist(self) -> None:
        assert len(self.budget.orphan_setsu) >= 1

    def test_orphan_setsu_content(self) -> None:
        orphan_names = {s.name for s in self.budget.orphan_setsu if s.number is not None}
        assert "需用費" in orphan_names or "委託料" in orphan_names

    def test_continuation_name(self) -> None:
        all_setsu = (
            *self.budget.orphan_setsu,
            *(s for m in self.budget.moku_records for s in m.setsu_list),
        )
        names = {s.name for s in all_setsu}
        assert any("負担金" in n and "交付金" in n for n in names)

    def test_sub_items(self) -> None:
        moku = self.budget.moku_records[0]
        ryohi = next((s for s in moku.setsu_list if s.name == "旅費"), None)
        assert ryohi is not None
        sub_names = {name for name, _ in ryohi.sub_items}
        assert "費用弁償" in sub_names
        assert "普通旅費" in sub_names

    def test_row_classification_coverage(self) -> None:
        classified = classify_all_rows(self.cells)
        kinds = {k for _, k in classified}
        assert "header" in kinds
        assert "moku" in kinds
        assert "setsu" in kinds
        assert "setsumei" in kinds

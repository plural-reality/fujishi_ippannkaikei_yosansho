"""
Tests for budget_cell.section — cell-layer 款/項 splitting.
"""

from __future__ import annotations

from budget_cell.parse import parse_page_budget
from budget_cell.section import split_page_sections
from budget_cell.types import Cell, PageHeader


def _cell(row: int, col: int, text: str) -> Cell:
    return Cell(
        row=row,
        col=col,
        x0=float(col * 10),
        y0=float(row * 10),
        x1=float((col + 1) * 10),
        y1=float((row + 1) * 10),
        text=text,
        words=(),
    )


def test_split_page_sections_drops_repeated_page_headers() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "２款 総務費"),
        _cell(1, 0, "１項"),
        _cell(1, 1, "総務管理費"),
        _cell(2, 0, "目"),
        _cell(2, 1, "本年度予算額"),
        _cell(2, 9, "節"),
        _cell(2, 11, "説明"),
        _cell(3, 0, "1 一般管理費"),
        _cell(3, 1, "2,074,044"),
        _cell(3, 9, "2 給料"),
        _cell(3, 10, "765,532"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    section_header, section_cells = sections[0]
    assert section_header == header
    assert {cell.row for cell in section_cells} == {3}

    budget = parse_page_budget(section_cells)
    assert tuple(record.name for record in budget.moku_records) == ("1 一般管理費",)


def test_split_page_sections_splits_on_mid_page_kou_transition_without_lines() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "1 一般管理費"),
        _cell(0, 1, "2,074,044"),
        _cell(0, 9, "2 給料"),
        _cell(0, 10, "765,532"),
        _cell(4, 0, "２項"),
        _cell(4, 1, "徴税費"),
        _cell(5, 0, "目"),
        _cell(5, 1, "本年度予算額"),
        _cell(5, 9, "節"),
        _cell(5, 11, "説明"),
        _cell(6, 0, "1 税務総務費"),
        _cell(6, 1, "648,430"),
        _cell(6, 9, "1 報酬"),
        _cell(6, 10, "14,346"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 2
    assert sections[0][0] == header
    assert {cell.row for cell in sections[0][1]} == {0}
    assert sections[1][0] == PageHeader("２", "総務費", "２", "徴税費")
    assert {cell.row for cell in sections[1][1]} == {6}


def test_split_page_sections_does_not_clobber_kou_name_from_combined_kan_kou_cell() -> None:
    header = PageHeader("１１", "災害復旧費", "１", "農林水産業施設災害復旧費")
    cells = (
        _cell(0, 0, "１１款 １項"),
        _cell(0, 1, "災害復旧費"),
        _cell(3, 0, "1 農地農業用施設災害復旧費"),
        _cell(3, 1, "52,000"),
        _cell(3, 9, "14 工事請負費"),
        _cell(3, 10, "52,000"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    assert sections[0][0] == header


def test_split_page_sections_drops_subtotal_rows_without_creating_moku() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "1 一般管理費"),
        _cell(0, 1, "2,074,044"),
        _cell(0, 9, "2 給料"),
        _cell(0, 10, "765,532"),
        _cell(1, 0, "計 ２款 総務費"),
        _cell(2, 0, "2 文書広報費"),
        _cell(2, 1, "191,399"),
        _cell(2, 9, "10 需用費"),
        _cell(2, 10, "5,704"),
    )

    sections = split_page_sections(header, cells)
    section_header, section_cells = sections[0]
    budget = parse_page_budget(section_cells)

    assert len(sections) == 1
    assert section_header == header
    assert {cell.row for cell in section_cells} == {0, 2}
    assert tuple(record.name for record in budget.moku_records) == ("1 一般管理費", "2 文書広報費")


def test_split_page_sections_keeps_same_kou_continuation_in_single_section() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "1 一般管理費"),
        _cell(0, 1, "2,074,044"),
        _cell(0, 9, "2 給料"),
        _cell(0, 10, "765,532"),
        _cell(4, 0, "２款 総務費"),
        _cell(5, 0, "１項"),
        _cell(5, 1, "総務管理費"),
        _cell(6, 0, "目"),
        _cell(6, 1, "本年度予算額"),
        _cell(6, 9, "節"),
        _cell(6, 11, "説明"),
        _cell(7, 0, "2 文書広報費"),
        _cell(7, 1, "191,399"),
        _cell(7, 9, "10 需用費"),
        _cell(7, 10, "5,704"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    assert sections[0][0] == header
    assert {cell.row for cell in sections[0][1]} == {0, 7}


def test_split_page_sections_reads_split_kou_tokens_without_words() -> None:
    header = PageHeader("２", "総務費", "６", "監査委員費")
    cells = (
        _cell(0, 0, "２"),
        _cell(0, 1, "款"),
        _cell(0, 2, "総務費"),
        _cell(1, 0, "１"),
        _cell(1, 1, "項"),
        _cell(1, 2, "総務管理費"),
        _cell(2, 0, "1 一般管理費"),
        _cell(2, 1, "2,074,044"),
        _cell(2, 9, "2 給料"),
        _cell(2, 10, "765,532"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    assert sections[0][0] == PageHeader("２", "総務費", "１", "総務管理費")
    assert {cell.row for cell in sections[0][1]} == {2}


def test_split_page_sections_drops_subtotal_row_before_kou_transition() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "1 一般管理費"),
        _cell(0, 1, "2,074,044"),
        _cell(0, 9, "2 給料"),
        _cell(0, 10, "765,532"),
        _cell(3, 0, "計 ２款 総務費"),
        _cell(4, 0, "２項"),
        _cell(4, 1, "徴税費"),
        _cell(5, 0, "1 税務総務費"),
        _cell(5, 1, "648,430"),
        _cell(5, 9, "1 報酬"),
        _cell(5, 10, "14,346"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 2
    assert sections[0][0] == header
    assert {cell.row for cell in sections[0][1]} == {0}
    assert sections[1][0] == PageHeader("２", "総務費", "２", "徴税費")
    assert {cell.row for cell in sections[1][1]} == {5}


def test_split_page_sections_keeps_same_kou_repeated_page_header_in_single_segment() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "1 一般管理費"),
        _cell(0, 1, "2,074,044"),
        _cell(0, 9, "2 給料"),
        _cell(0, 10, "765,532"),
        _cell(3, 0, "２款 総務費"),
        _cell(4, 0, "１項"),
        _cell(4, 1, "総務管理費"),
        _cell(5, 0, "目"),
        _cell(5, 1, "本年度予算額"),
        _cell(5, 9, "節"),
        _cell(5, 11, "説明"),
        _cell(6, 9, "3 職員手当等"),
        _cell(6, 10, "99,587"),
        _cell(6, 11, "001 給与費 296"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    assert sections[0][0] == header
    assert {cell.row for cell in sections[0][1]} == {0, 6}


def test_split_page_sections_handles_split_kou_tokens_across_cells() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "1 一般管理費"),
        _cell(0, 1, "2,074,044"),
        _cell(0, 9, "2 給料"),
        _cell(0, 10, "765,532"),
        _cell(4, 0, "２"),
        _cell(4, 1, "項"),
        _cell(4, 2, "徴税費"),
        _cell(5, 0, "1 税務総務費"),
        _cell(5, 1, "648,430"),
        _cell(5, 9, "1 報酬"),
        _cell(5, 10, "14,346"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 2
    assert sections[1][0] == PageHeader("２", "総務費", "２", "徴税費")
    assert {cell.row for cell in sections[1][1]} == {5}


def test_split_page_sections_keeps_same_kou_page_continuation_as_single_section() -> None:
    header = PageHeader("３", "民生費", "１", "社会福祉費")
    cells = (
        _cell(0, 0, "３款 民生費"),
        _cell(1, 0, "１項"),
        _cell(1, 1, "社会福祉費"),
        _cell(2, 9, "節"),
        _cell(2, 11, "説明"),
        _cell(3, 9, "1 報酬"),
        _cell(3, 10, "1,000"),
        _cell(3, 11, "001 継続事業"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    assert sections[0][0] == header
    assert {cell.row for cell in sections[0][1]} == {3}

    budget = parse_page_budget(sections[0][1])
    assert budget.moku_records == ()
    assert tuple(record.name for record in budget.orphan_setsu) == ("報酬",)


def test_split_page_sections_drops_subtotal_rows_without_creating_new_section() -> None:
    header = PageHeader("２", "総務費", "１", "総務管理費")
    cells = (
        _cell(0, 0, "計 ２款 総務費"),
        _cell(1, 0, "1 一般管理費"),
        _cell(1, 1, "2,074,044"),
        _cell(1, 9, "2 給料"),
        _cell(1, 10, "765,532"),
    )

    sections = split_page_sections(header, cells)

    assert len(sections) == 1
    assert {cell.row for cell in sections[0][1]} == {1}

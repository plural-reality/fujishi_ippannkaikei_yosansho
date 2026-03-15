from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from budget_cell.excel_io import read_rows_from_excel_path
from budget_cell.flatten import FFILL_FIELDS, sectioned_ffill
from budget_cell.pipeline import rows_from_pdf
from budget_cell.types import FlatRow


ROOT = Path(__file__).resolve().parent.parent
R6_PDF = ROOT / "tests" / "fixtures" / "r6" / "input" / "budget-spread.pdf"
R6_SHORT = ROOT / "tests" / "fixtures" / "r6" / "expected" / "budget-spread-short.xlsx"
R6_LONG = ROOT / "tests" / "fixtures" / "r6" / "expected" / "budget-spread-long.xlsx"
_KOU_AS_MOKU_RE = re.compile(r"^[0-9０-９]+項$")
_FOOTER_PAGE_RE = re.compile(r"^-\s*[0-9０-９]+\s*-$")

pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in (R6_PDF, R6_SHORT, R6_LONG)),
    reason="R6 regression fixtures not present",
)


@lru_cache(maxsize=1)
def _pdf_rows() -> tuple[FlatRow, ...]:
    rows = rows_from_pdf(str(R6_PDF), ffill_fields=None)
    return sectioned_ffill(rows, FFILL_FIELDS, key_fn=lambda row: (row.kan_name, row.kou_name))


@lru_cache(maxsize=1)
def _short_rows() -> tuple[FlatRow, ...]:
    return read_rows_from_excel_path(str(R6_SHORT))


@lru_cache(maxsize=1)
def _long_rows() -> tuple[FlatRow, ...]:
    return read_rows_from_excel_path(str(R6_LONG))


def _kou_moku_hits(rows: tuple[FlatRow, ...]) -> tuple[tuple[int, FlatRow], ...]:
    return tuple(
        (index, row)
        for index, row in enumerate(rows, start=2)
        if bool(_KOU_AS_MOKU_RE.search(row.moku_name))
    )


def _footer_page_hits(rows: tuple[FlatRow, ...]) -> tuple[tuple[int, FlatRow], ...]:
    return tuple(
        (index, row)
        for index, row in enumerate(rows, start=2)
        if bool(_FOOTER_PAGE_RE.match(row.setsumei_name.strip()))
    )


def _strip_path(row: FlatRow) -> FlatRow:
    """Strip setsumei_path for comparison with pre-path Excel fixtures."""
    return replace(row, setsumei_path=())


def _normalize_for_wide_projection(row: FlatRow) -> FlatRow:
    return replace(row, setsumei_level=row.setsumei_level if row.setsumei_name else None)


def test_r6_pdf_rows_do_not_promote_kou_to_moku() -> None:
    assert _kou_moku_hits(_pdf_rows()) == ()


def test_r6_short_workbook_has_no_kou_marker_in_moku_column() -> None:
    assert _kou_moku_hits(_short_rows()) == ()


def test_r6_long_workbook_has_no_kou_marker_in_moku_column() -> None:
    assert _kou_moku_hits(_long_rows()) == ()


def test_r6_pdf_rows_have_no_footer_page_numbers_in_setsumei() -> None:
    assert _footer_page_hits(_pdf_rows()) == ()


def test_r6_short_workbook_has_no_footer_page_numbers_in_setsumei() -> None:
    assert _footer_page_hits(_short_rows()) == ()


def test_r6_long_workbook_has_no_footer_page_numbers_in_setsumei() -> None:
    assert _footer_page_hits(_long_rows()) == ()


def test_r6_long_workbook_matches_current_pdf_pipeline_exactly() -> None:
    assert _long_rows() == tuple(map(_strip_path, _pdf_rows()))


def test_r6_short_workbook_matches_current_pdf_pipeline_after_wide_normalization() -> None:
    assert tuple(map(lambda r: _strip_path(_normalize_for_wide_projection(r)), _pdf_rows())) == _short_rows()

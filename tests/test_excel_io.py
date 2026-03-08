from __future__ import annotations

from budget_cell.excel_io import read_rows_from_excel_bytes, write_rows_to_excel_bytes
from budget_cell.types import FlatRow


def _row(**overrides) -> FlatRow:
    defaults = dict(
        kan_name="議会費",
        kou_name="議会費",
        moku_name="1 議会費",
        honendo=488451,
        zenendo=499446,
        hikaku=-10995,
        kokuken=None,
        chihousei=None,
        sonota=1013,
        ippan=487438,
        setsu_number=1,
        setsu_name="報酬",
        setsu_amount=205920,
        sub_item_name="",
        sub_item_amount=None,
        setsumei_code="001",
        setsumei_level=1,
        setsumei_name="給与費",
        setsumei_amount=448879,
    )
    return FlatRow(**{**defaults, **overrides})


def test_wide_excel_round_trip() -> None:
    rows = (
        _row(),
        _row(setsumei_level=2, setsumei_name="市議会議員 32人", setsumei_amount=352146),
        _row(setsumei_code="", setsumei_level=None, setsumei_name="", setsumei_amount=None),
    )
    workbook_bytes = write_rows_to_excel_bytes(rows, layout="wide")
    restored = read_rows_from_excel_bytes(workbook_bytes)
    assert restored == rows


def test_long_excel_round_trip() -> None:
    rows = (
        _row(),
        _row(setsumei_level=3, setsumei_name="補足", setsumei_amount=None),
    )
    workbook_bytes = write_rows_to_excel_bytes(rows, layout="long")
    restored = read_rows_from_excel_bytes(workbook_bytes)
    assert restored == rows

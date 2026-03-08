from __future__ import annotations

from io import StringIO

from budget_cell.row_stream import read_rows_ndjson, write_rows_ndjson
from budget_cell.types import FlatRow


def _sample_row(**overrides) -> FlatRow:
    defaults = dict(
        kan_name="総務費",
        kou_name="総務管理費",
        moku_name="1 一般管理費",
        honendo=100,
        zenendo=90,
        hikaku=10,
        kokuken=None,
        chihousei=None,
        sonota=5,
        ippan=95,
        setsu_number=1,
        setsu_name="報酬",
        setsu_amount=100,
        sub_item_name="",
        sub_item_amount=None,
        setsumei_code="001",
        setsumei_level=1,
        setsumei_name="給与費",
        setsumei_amount=80,
    )
    return FlatRow(**{**defaults, **overrides})


def test_ndjson_round_trip() -> None:
    rows = (
        _sample_row(),
        _sample_row(setsumei_code="", setsumei_level=2, setsumei_name="一般職 11人"),
    )
    buffer = StringIO()
    write_rows_ndjson(buffer, rows)
    restored = read_rows_ndjson(StringIO(buffer.getvalue()))
    assert restored == rows

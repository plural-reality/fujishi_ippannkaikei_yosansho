from __future__ import annotations

from budget_cell.matchers import trend_key_match_id_loose
from budget_cell.trend import aggregate_trends, rows_to_trend_nodes, trend_key_match_id_strict
from budget_cell.types import FlatRow


def _row(**overrides) -> FlatRow:
    defaults = dict(
        kan_name="総務費",
        kou_name="総務管理費",
        moku_name="1 一般管理費",
        honendo=100,
        zenendo=90,
        hikaku=10,
        kokuken=None,
        chihousei=None,
        sonota=0,
        ippan=100,
        setsu_number=3,
        setsu_name="職員手当等",
        setsu_amount=100,
        sub_item_name="",
        sub_item_amount=None,
        setsumei_code="001",
        setsumei_level=1,
        setsumei_name="給与費",
        setsumei_amount=50,
    )
    return FlatRow(**{**defaults, **overrides})


def test_rows_to_trend_nodes_builds_paths() -> None:
    rows = (
        _row(setsumei_level=1, setsumei_name="給与費", setsumei_amount=120),
        _row(setsumei_level=2, setsumei_name="一般職", setsumei_amount=80),
    )
    nodes = rows_to_trend_nodes("R8", rows)
    assert len(nodes) == 2
    assert nodes[0].key.path_levels == ("給与費",)
    assert nodes[1].key.path_levels == ("給与費", "一般職")


def test_aggregate_trends_diff_and_status() -> None:
    r7 = rows_to_trend_nodes("R7", (_row(setsumei_amount=100),))
    r8 = rows_to_trend_nodes("R8", (_row(setsumei_amount=130),))
    years, rows = aggregate_trends((*r7, *r8))
    assert years == ("R7", "R8")
    assert len(rows) == 1
    row = rows[0]
    assert row.year_amounts == (100, 130)
    assert row.diff == 30
    assert row.status == "増額"


def test_aggregate_trends_strict_keeps_notational_variants_separate() -> None:
    r7 = rows_to_trend_nodes(
        "R7",
        (
            _row(
                moku_name="１ 一般管理費",
                setsumei_name="給与 費",
                setsumei_amount=100,
            ),
        ),
    )
    r8 = rows_to_trend_nodes(
        "R8",
        (
            _row(
                moku_name="1一般管理費",
                setsumei_name="給与費",
                setsumei_amount=130,
            ),
        ),
    )
    years, rows = aggregate_trends(
        (*r7, *r8),
        match_id_fn=trend_key_match_id_strict,
    )
    assert years == ("R7", "R8")
    assert len(rows) == 2
    assert {row.year_amounts for row in rows} == {(100, 0), (0, 130)}


def test_aggregate_trends_loose_merges_notational_variants() -> None:
    r7 = rows_to_trend_nodes(
        "R7",
        (
            _row(
                moku_name="１ 一般管理費",
                setsumei_name="給与 費",
                setsumei_amount=100,
            ),
        ),
    )
    r8 = rows_to_trend_nodes(
        "R8",
        (
            _row(
                moku_name="1一般管理費",
                setsumei_name="給与費",
                setsumei_amount=130,
            ),
        ),
    )
    years, rows = aggregate_trends(
        (*r7, *r8),
        match_id_fn=trend_key_match_id_loose,
    )
    assert years == ("R7", "R8")
    assert len(rows) == 1
    assert rows[0].year_amounts == (100, 130)
    assert rows[0].diff == 30

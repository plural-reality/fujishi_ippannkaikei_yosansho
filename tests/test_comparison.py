from __future__ import annotations

from budget_cell.matchers import comparison_key_match_id_loose
from budget_cell.comparison import aggregate_comparisons, rows_to_comparison_nodes, comparison_key_match_id_strict
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


def _find_node(nodes, node_kind, path_levels):
    return next(node for node in nodes if node.key.node_kind == node_kind and node.key.path_levels == path_levels)


def _find_row(rows, node_kind, path_levels):
    return next(row for row in rows if row.key.node_kind == node_kind and row.key.path_levels == path_levels)


def test_rows_to_comparison_nodes_builds_parallel_branches() -> None:
    rows = (
        _row(
            sub_item_name="会計年度任用職員", sub_item_amount=40,
            setsumei_level=1, setsumei_name="給与費", setsumei_amount=120,
            setsumei_path=("給与費",),
        ),
        _row(
            setsumei_level=2, setsumei_name="一般職", setsumei_amount=80,
            setsumei_path=("給与費", "一般職"),
        ),
    )
    nodes = rows_to_comparison_nodes("R8", rows)
    assert len(nodes) == 4
    assert _find_node(nodes, "節", ("3 職員手当等",)).amount == 100
    assert _find_node(nodes, "小区分", ("3 職員手当等", "会計年度任用職員")).amount == 40
    assert _find_node(nodes, "説明", ("給与費",)).amount == 120
    assert _find_node(nodes, "説明", ("給与費", "一般職")).amount == 80


def test_aggregate_comparisons_diff_and_status() -> None:
    r7 = rows_to_comparison_nodes("R7", (_row(setsumei_amount=100, setsumei_path=("給与費",)),))
    r8 = rows_to_comparison_nodes("R8", (_row(setsumei_amount=130, setsumei_path=("給与費",)),))
    years, rows = aggregate_comparisons((*r7, *r8))
    assert years == ("R7", "R8")
    assert len(rows) == 2
    assert _find_row(rows, "節", ("3 職員手当等",)).year_amounts == (100, 100)
    setsumei_row = _find_row(rows, "説明", ("給与費",))
    assert setsumei_row.year_amounts == (100, 130)
    assert setsumei_row.diff == 30
    assert setsumei_row.status == "増額"


def test_aggregate_comparisons_strict_keeps_notational_variants_separate() -> None:
    r7 = rows_to_comparison_nodes(
        "R7",
        (
            _row(
                moku_name="１ 一般管理費",
                setsumei_name="給与 費",
                setsumei_amount=100,
            ),
        ),
    )
    r8 = rows_to_comparison_nodes(
        "R8",
        (
            _row(
                moku_name="1一般管理費",
                setsumei_name="給与費",
                setsumei_amount=130,
            ),
        ),
    )
    years, rows = aggregate_comparisons(
        (*r7, *r8),
        match_id_fn=comparison_key_match_id_strict,
    )
    assert years == ("R7", "R8")
    explanation_rows = tuple(row for row in rows if row.key.node_kind == "説明")
    assert len(explanation_rows) == 2
    assert {row.year_amounts for row in explanation_rows} == {(100, 0), (0, 130)}


def test_aggregate_comparisons_loose_merges_notational_variants() -> None:
    r7 = rows_to_comparison_nodes(
        "R7",
        (
            _row(
                moku_name="１ 一般管理費",
                setsumei_name="給与 費",
                setsumei_amount=100,
            ),
        ),
    )
    r8 = rows_to_comparison_nodes(
        "R8",
        (
            _row(
                moku_name="1一般管理費",
                setsumei_name="給与費",
                setsumei_amount=130,
            ),
        ),
    )
    years, rows = aggregate_comparisons(
        (*r7, *r8),
        match_id_fn=comparison_key_match_id_loose,
    )
    assert years == ("R7", "R8")
    explanation_rows = tuple(row for row in rows if row.key.node_kind == "説明")
    assert len(explanation_rows) == 1
    assert explanation_rows[0].year_amounts == (100, 130)
    assert explanation_rows[0].diff == 30


def test_cross_code_parent_child_uses_setsumei_path() -> None:
    """Regression: L2 with different code from L1 must inherit correct L1 parent.

    R8 消防指令センター: L1 code='006', L2 code='001'.
    Previously _advance_path keyed by code, so L2 picked up wrong L1.
    With setsumei_path from parse layer, path is authoritative.
    """
    rows = (
        # L1 code='006' — 消防指令センター費
        _row(
            moku_name="消防費",
            setsumei_code="006",
            setsumei_level=1,
            setsumei_name="富士市・富士宮市消防指令センター費",
            setsumei_amount=1852791,
            setsumei_path=("富士市・富士宮市消防指令センター費",),
        ),
        # L2 code='001' — different code from L1!
        _row(
            moku_name="消防費",
            setsumei_code="001",
            setsumei_level=2,
            setsumei_name="富士市・富士宮市消防指令センター運営事業費",
            setsumei_amount=1852791,
            setsumei_path=("富士市・富士宮市消防指令センター費", "富士市・富士宮市消防指令センター運営事業費"),
        ),
    )
    nodes = rows_to_comparison_nodes("R8", rows)
    l2_node = _find_node(
        nodes, "説明",
        ("富士市・富士宮市消防指令センター費", "富士市・富士宮市消防指令センター運営事業費"),
    )
    assert l2_node.amount == 1852791
    # L1 should be 消防指令センター費, NOT 救急活動費
    assert l2_node.key.path_levels[0] == "富士市・富士宮市消防指令センター費"


def test_fallback_path_without_setsumei_path() -> None:
    """Legacy Excel without setsumei_path falls back to _advance_path (moku-keyed)."""
    rows = (
        _row(setsumei_level=1, setsumei_name="給与費", setsumei_amount=100),
        _row(setsumei_level=2, setsumei_name="一般職", setsumei_amount=80),
    )
    nodes = rows_to_comparison_nodes("R8", rows)
    assert _find_node(nodes, "説明", ("給与費",)).amount == 100
    assert _find_node(nodes, "説明", ("給与費", "一般職")).amount == 80


def test_aggregate_comparisons_distinguishes_setsu_and_setsumei_with_same_label() -> None:
    r7 = rows_to_comparison_nodes(
        "R7",
        (
            _row(
                setsu_number=1,
                setsu_name="給与費",
                setsu_amount=200,
                setsumei_name="給与費",
                setsumei_amount=100,
            ),
        ),
    )
    years, rows = aggregate_comparisons(r7)
    assert years == ("R7",)
    assert len(rows) == 2
    assert _find_row(rows, "節", ("1 給与費",)).year_amounts == (200,)
    assert _find_row(rows, "説明", ("給与費",)).year_amounts == (100,)

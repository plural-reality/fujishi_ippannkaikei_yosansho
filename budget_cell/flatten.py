"""
Pure flatten: PageBudget → FlatRow[].

Two orthogonal transforms:
  1. flatten  — structural: PageBudget tree → flat rows (concatMap)
  2. ffill    — tabular:    forward-fill empty cells from row above (scanl)

Depends only on types. No IO, no PDF knowledge.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from budget_cell.types import (
    FlatRow,
    MokuRecord,
    PageBudget,
    SetsuRecord,
    SetsumeiEntry,
)


# ---------------------------------------------------------------------------
# Column headers
# ---------------------------------------------------------------------------

HEADERS: tuple[str, ...] = (
    "目", "本年度予算額", "前年度予算額", "比較",
    "国県支出金", "地方債", "その他", "一般財源",
    "節番号", "節名", "節金額",
    "小区分", "小区分金額",
    "事業コード", "説明", "説明金額",
)

MOKU_FIELDS: tuple[str, ...] = (
    "moku_name", "honendo", "zenendo", "hikaku",
    "kokuken", "chihousei", "sonota", "ippan",
)

SETSU_FIELDS: tuple[str, ...] = (
    "setsu_number", "setsu_name", "setsu_amount",
)

FFILL_FIELDS: tuple[str, ...] = (*MOKU_FIELDS, *SETSU_FIELDS)


# ---------------------------------------------------------------------------
# 1. Structural flatten (concatMap)
# ---------------------------------------------------------------------------

def _setsumei_row(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    entry: SetsumeiEntry,
) -> FlatRow:
    return FlatRow(
        moku_name=moku.name if moku else "",
        honendo=moku.honendo if moku else None,
        zenendo=moku.zenendo if moku else None,
        hikaku=moku.hikaku if moku else None,
        kokuken=moku.zaigen.kokuken if moku else None,
        chihousei=moku.zaigen.chihousei if moku else None,
        sonota=moku.zaigen.sonota if moku else None,
        ippan=moku.zaigen.ippan if moku else None,
        setsu_number=setsu.number,
        setsu_name=setsu.name,
        setsu_amount=setsu.amount,
        sub_item_name="",
        sub_item_amount=None,
        setsumei_code=entry.code or "",
        setsumei_name=entry.name,
        setsumei_amount=entry.amount,
    )


def _sub_item_row(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    name: str,
    amount: int | None,
) -> FlatRow:
    return FlatRow(
        moku_name=moku.name if moku else "",
        honendo=moku.honendo if moku else None,
        zenendo=moku.zenendo if moku else None,
        hikaku=moku.hikaku if moku else None,
        kokuken=moku.zaigen.kokuken if moku else None,
        chihousei=moku.zaigen.chihousei if moku else None,
        sonota=moku.zaigen.sonota if moku else None,
        ippan=moku.zaigen.ippan if moku else None,
        setsu_number=setsu.number,
        setsu_name=setsu.name,
        setsu_amount=setsu.amount,
        sub_item_name=name,
        sub_item_amount=amount,
        setsumei_code="",
        setsumei_name="",
        setsumei_amount=None,
    )


def _setsu_only_row(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
) -> FlatRow:
    return FlatRow(
        moku_name=moku.name if moku else "",
        honendo=moku.honendo if moku else None,
        zenendo=moku.zenendo if moku else None,
        hikaku=moku.hikaku if moku else None,
        kokuken=moku.zaigen.kokuken if moku else None,
        chihousei=moku.zaigen.chihousei if moku else None,
        sonota=moku.zaigen.sonota if moku else None,
        ippan=moku.zaigen.ippan if moku else None,
        setsu_number=setsu.number,
        setsu_name=setsu.name,
        setsu_amount=setsu.amount,
        sub_item_name="",
        sub_item_amount=None,
        setsumei_code="",
        setsumei_name="",
        setsumei_amount=None,
    )


def flatten_setsu(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
) -> tuple[FlatRow, ...]:
    """Flatten one SetsuRecord into FlatRows (sub-items + setsumei entries)."""
    sub_rows = tuple(
        _sub_item_row(moku, setsu, name, amount)
        for name, amount in setsu.sub_items
    )
    setsumei_rows = tuple(
        _setsumei_row(moku, setsu, entry)
        for entry in setsu.setsumei
    )
    return (
        (*sub_rows, *setsumei_rows)
        if sub_rows or setsumei_rows
        else (_setsu_only_row(moku, setsu),)
    )


def flatten_moku(moku: MokuRecord) -> tuple[FlatRow, ...]:
    return tuple(
        row
        for setsu in moku.setsu_list
        for row in flatten_setsu(moku, setsu)
    )


def flatten_orphans(orphan_setsu: Sequence[SetsuRecord]) -> tuple[FlatRow, ...]:
    """Orphans have no moku on this page — fields left empty for ffill."""
    return tuple(
        row
        for setsu in orphan_setsu
        for row in flatten_setsu(None, setsu)
    )


def flatten_page_budget(budget: PageBudget) -> tuple[FlatRow, ...]:
    return (
        *flatten_orphans(budget.orphan_setsu),
        *(row for moku in budget.moku_records for row in flatten_moku(moku)),
    )


def flatten_all_pages(budgets: Sequence[PageBudget]) -> tuple[FlatRow, ...]:
    """Pure concatMap over pages. No cross-page logic."""
    return tuple(
        row
        for budget in budgets
        for row in flatten_page_budget(budget)
    )


# ---------------------------------------------------------------------------
# 2. Generic forward-fill (scanl)
# ---------------------------------------------------------------------------

def _is_empty(val: object) -> bool:
    return val is None or val == ""


def ffill(
    rows: Sequence[FlatRow],
    fields: tuple[str, ...],
) -> tuple[FlatRow, ...]:
    """Forward-fill: for specified fields, empty values inherit from the previous row.

    Pure scanl — no domain knowledge, just tabular forward-fill.
    """
    def step(
        acc: tuple[FlatRow | None, tuple[FlatRow, ...]],
        row: FlatRow,
    ) -> tuple[FlatRow | None, tuple[FlatRow, ...]]:
        prev, filled = acc
        replacements = (
            {
                f: getattr(prev, f)
                for f in fields
                if _is_empty(getattr(row, f)) and not _is_empty(getattr(prev, f))
            }
            if prev is not None
            else {}
        )
        new_row = replace(row, **replacements) if replacements else row
        return (new_row, (*filled, new_row))

    result: tuple[FlatRow | None, tuple[FlatRow, ...]] = (None, ())
    for row in rows:
        result = step(result, row)
    return result[1]


# ---------------------------------------------------------------------------
# Row → tuple (for CSV/tabular output)
# ---------------------------------------------------------------------------

def row_to_tuple(row: FlatRow) -> tuple:
    return (
        row.moku_name,
        row.honendo or "",
        row.zenendo or "",
        row.hikaku or "",
        row.kokuken or "",
        row.chihousei or "",
        row.sonota or "",
        row.ippan or "",
        row.setsu_number or "",
        row.setsu_name,
        row.setsu_amount or "",
        row.sub_item_name,
        row.sub_item_amount or "",
        row.setsumei_code,
        row.setsumei_name,
        row.setsumei_amount or "",
    )


def to_table(budget: PageBudget) -> tuple[tuple[str, ...], ...]:
    rows = flatten_page_budget(budget)
    return (HEADERS, *(row_to_tuple(r) for r in rows))

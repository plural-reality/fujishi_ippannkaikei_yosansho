"""
Pure flatten: PageBudget → FlatRow[].

Depends only on types. No IO, no PDF knowledge.
"""

from __future__ import annotations

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
    "orphan",
)


# ---------------------------------------------------------------------------
# Pure flatten transforms
# ---------------------------------------------------------------------------

def _setsumei_row(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    entry: SetsumeiEntry,
    is_orphan: bool,
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
        is_orphan=is_orphan,
    )


def _sub_item_row(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    name: str,
    amount: int | None,
    is_orphan: bool,
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
        is_orphan=is_orphan,
    )


def _setsu_only_row(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    is_orphan: bool,
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
        is_orphan=is_orphan,
    )


def flatten_setsu(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    is_orphan: bool = False,
) -> tuple[FlatRow, ...]:
    """Flatten one SetsuRecord into FlatRows (sub-items + setsumei entries)."""
    sub_rows = tuple(
        _sub_item_row(moku, setsu, name, amount, is_orphan)
        for name, amount in setsu.sub_items
    )
    setsumei_rows = tuple(
        _setsumei_row(moku, setsu, entry, is_orphan)
        for entry in setsu.setsumei
    )
    return (
        (*sub_rows, *setsumei_rows)
        if sub_rows or setsumei_rows
        else (_setsu_only_row(moku, setsu, is_orphan),)
    )


def flatten_moku(moku: MokuRecord) -> tuple[FlatRow, ...]:
    return tuple(
        row
        for setsu in moku.setsu_list
        for row in flatten_setsu(moku, setsu)
    )


def flatten_orphans(orphan_setsu: Sequence[SetsuRecord]) -> tuple[FlatRow, ...]:
    return tuple(
        row
        for setsu in orphan_setsu
        for row in flatten_setsu(None, setsu, is_orphan=True)
    )


def flatten_page_budget(budget: PageBudget) -> tuple[FlatRow, ...]:
    return (
        *flatten_orphans(budget.orphan_setsu),
        *(row for moku in budget.moku_records for row in flatten_moku(moku)),
    )


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
        "orphan" if row.is_orphan else "",
    )


def to_table(budget: PageBudget) -> tuple[tuple[str, ...], ...]:
    rows = flatten_page_budget(budget)
    return (HEADERS, *(row_to_tuple(r) for r in rows))

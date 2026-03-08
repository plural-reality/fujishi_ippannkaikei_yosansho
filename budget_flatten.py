"""
Budget Flatten — Pure transform from hierarchical PageBudget to flat table rows.

Depends only on domain types from budget_parse. No PDF/cell/IO knowledge.

  PageBudget → flatten_page_budget → tuple[FlatRow, ...]

FlatRow is the sole interface to any output format (CSV, Excel, stdout).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from budget_parse import (
    MokuRecord,
    PageBudget,
    SetsuRecord,
    SetsumeiEntry,
)


# ---------------------------------------------------------------------------
# Output type (the interface)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlatRow:
    """Non-normalized single row — carries full context from 目 to 説明."""
    moku_name: str
    honendo: int | None
    zenendo: int | None
    hikaku: int | None
    kokuken: int | None
    chihousei: int | None
    sonota: int | None
    ippan: int | None
    setsu_number: int | None
    setsu_name: str
    setsu_amount: int | None
    sub_item_name: str
    sub_item_amount: int | None
    setsumei_code: str
    setsumei_name: str
    setsumei_amount: int | None
    is_orphan: bool  # True if 目 is on a previous page


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

def _setsumei_rows(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    entry: SetsumeiEntry,
    is_orphan: bool,
) -> FlatRow:
    """One FlatRow per SetsumeiEntry."""
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


def _sub_item_rows(
    moku: MokuRecord | None,
    setsu: SetsuRecord,
    name: str,
    amount: int | None,
    is_orphan: bool,
) -> FlatRow:
    """One FlatRow per sub-item."""
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
    """Fallback row when a setsu has neither sub-items nor setsumei."""
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
        _sub_item_rows(moku, setsu, name, amount, is_orphan)
        for name, amount in setsu.sub_items
    )
    setsumei_rows = tuple(
        _setsumei_rows(moku, setsu, entry, is_orphan)
        for entry in setsu.setsumei
    )
    return (
        (*sub_rows, *setsumei_rows)
        if sub_rows or setsumei_rows
        else (_setsu_only_row(moku, setsu, is_orphan),)
    )


def flatten_moku(moku: MokuRecord) -> tuple[FlatRow, ...]:
    """Flatten one MokuRecord into FlatRows (flatMap over setsu_list)."""
    return tuple(
        row
        for setsu in moku.setsu_list
        for row in flatten_setsu(moku, setsu)
    )


def flatten_orphans(orphan_setsu: Sequence[SetsuRecord]) -> tuple[FlatRow, ...]:
    """Flatten orphan setsu (no 目 on this page) into FlatRows."""
    return tuple(
        row
        for setsu in orphan_setsu
        for row in flatten_setsu(None, setsu, is_orphan=True)
    )


def flatten_page_budget(budget: PageBudget) -> tuple[FlatRow, ...]:
    """
    Top-level flatten: PageBudget → tuple[FlatRow, ...].

    This is a pure flatMap:
      orphans.flatMap(flatten_setsu) ++ moku_records.flatMap(flatten_moku)
    """
    return (
        *flatten_orphans(budget.orphan_setsu),
        *(row for moku in budget.moku_records for row in flatten_moku(moku)),
    )


# ---------------------------------------------------------------------------
# Row → tuple (for CSV/tabular output)
# ---------------------------------------------------------------------------

def row_to_tuple(row: FlatRow) -> tuple:
    """Convert FlatRow to a plain tuple matching HEADERS order."""
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
    """PageBudget → full table with headers. Ready for CSV/Excel."""
    rows = flatten_page_budget(budget)
    return (HEADERS, *(row_to_tuple(r) for r in rows))

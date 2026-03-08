"""
Pure budget parsing: Cell[] → PageBudget.

Pipeline (all pure, composable):
  tuple[Cell, ...] → CellIndex → classify_all_rows → group_rows_by_moku
    → group_rows_by_setsu → build records → PageBudget

No IO. Depends only on types.
"""

from __future__ import annotations

import re
from functools import reduce
from itertools import takewhile
from types import MappingProxyType
from typing import Mapping, Sequence

from budget_cell.types import (
    Cell,
    MokuRecord,
    PageBudget,
    SetsuRecord,
    SetsumeiEntry,
    Zaigen,
)


# ---------------------------------------------------------------------------
# Column index constants (budget table schema)
# ---------------------------------------------------------------------------

COL_MOKU = 0
COL_HONENDO = 1
COL_ZENENDO = 2
COL_HIKAKU = 3
COL_KOKUKEN = 4
COL_CHIHOUSEI = 5
COL_SONOTA = 6
COL_IPPAN = 7
COL_KUBUN = 9
COL_KINGAKU = 10
COL_SETSUMEI = 11


# ---------------------------------------------------------------------------
# Parsing primitives (pure)
# ---------------------------------------------------------------------------

def parse_amount(text: str) -> int | None:
    """'85,912' → 85912, '△1,594' → -1594, '' → None."""
    stripped = text.strip()
    negative = stripped.startswith("△") or stripped.startswith("-")
    digits = re.sub(r"[^\d]", "", stripped)
    return (
        None if not digits else
        -int(digits) if negative else
        int(digits)
    )


def parse_setsu_text(text: str) -> tuple[int, str] | None:
    """'10 需用費' → (10, '需用費'). None if not a 節 pattern."""
    m = re.match(r"^(\d+)\s+(.+)$", text.strip())
    return (int(m.group(1)), m.group(2)) if m else None


def parse_setsumei_line(text: str) -> SetsumeiEntry:
    """Parse a single line from the 説明 column into a typed entry."""
    stripped = text.strip()
    m = re.match(r"^(\d{3})\s+(.+?)\s+([\d,]+)$", stripped)
    return (
        SetsumeiEntry("coded", m.group(1), m.group(2), parse_amount(m.group(3)))
        if m else _parse_setsumei_no_full_code(stripped)
    )


def _parse_setsumei_no_full_code(stripped: str) -> SetsumeiEntry:
    m = re.match(r"^(\d{3})\s+(.+)$", stripped)
    return (
        SetsumeiEntry("coded", m.group(1), m.group(2), None)
        if m else _parse_setsumei_text(stripped)
    )


def _parse_setsumei_text(stripped: str) -> SetsumeiEntry:
    m = re.match(r"^(.+?)\s+([\d,]+)$", stripped)
    return (
        SetsumeiEntry("text", None, m.group(1), parse_amount(m.group(2)))
        if m and not re.search(r"\d$", m.group(1))
        else SetsumeiEntry("text", None, stripped, None)
    )


# ---------------------------------------------------------------------------
# Cell index (immutable lookup)
# ---------------------------------------------------------------------------

CellIndex = Mapping[tuple[int, int], str]


def build_cell_index(cells: Sequence[Cell]) -> CellIndex:
    """Immutable (row, col) → text mapping."""
    return MappingProxyType({(c.row, c.col): c.text for c in cells})


def text_at(idx: CellIndex, row: int, col: int) -> str | None:
    """Lookup cell text. None if absent."""
    return idx.get((row, col))


def all_rows(cells: Sequence[Cell]) -> tuple[int, ...]:
    """All unique row indices, sorted."""
    return tuple(sorted({c.row for c in cells}))


# ---------------------------------------------------------------------------
# Header detection (pure)
# ---------------------------------------------------------------------------

_HEADER_TOKENS = frozenset({
    "目", "千円", "節", "本年度予算額", "前年度予算額",
    "一般財源", "国県支出金", "地方債", "その他",
    "区分", "金額", "説明", "比較",
})


def _normalize(text: str) -> str:
    return text.strip().replace(" ", "").replace("\n", "").replace("\u3000", "")


def is_header_row(idx: CellIndex, row: int) -> bool:
    """True if any cell in this row contains a known header keyword."""
    texts = frozenset(
        _normalize(v) for (r, _), v in idx.items() if r == row
    )
    return bool(texts & _HEADER_TOKENS)


def detect_header_rows(cells: Sequence[Cell]) -> frozenset[int]:
    """Find all header row indices."""
    idx = build_cell_index(cells)
    return frozenset(r for r in all_rows(cells) if is_header_row(idx, r))


# ---------------------------------------------------------------------------
# Row predicates (pure, focused)
# ---------------------------------------------------------------------------

def _has_text(idx: CellIndex, row: int, col: int) -> bool:
    t = text_at(idx, row, col)
    return t is not None and bool(t.strip())


def _is_setsu(idx: CellIndex, row: int) -> bool:
    return (
        _has_text(idx, row, COL_KUBUN)
        and _has_text(idx, row, COL_KINGAKU)
        and parse_setsu_text(text_at(idx, row, COL_KUBUN) or "") is not None
    )


def _is_sub_item(idx: CellIndex, row: int) -> bool:
    return (
        _has_text(idx, row, COL_KUBUN)
        and _has_text(idx, row, COL_KINGAKU)
        and parse_setsu_text(text_at(idx, row, COL_KUBUN) or "") is None
    )


def _is_continuation(idx: CellIndex, row: int) -> bool:
    return _has_text(idx, row, COL_KUBUN) and not _has_text(idx, row, COL_KINGAKU)


# ---------------------------------------------------------------------------
# Row classification (pure)
# ---------------------------------------------------------------------------

def classify_row(idx: CellIndex, row: int, headers: frozenset[int]) -> str:
    return (
        "header" if row in headers else
        "moku" if _has_text(idx, row, COL_MOKU) else
        "setsu" if _is_setsu(idx, row) else
        "sub_item" if _is_sub_item(idx, row) else
        "continuation" if _is_continuation(idx, row) else
        "setsumei" if _has_text(idx, row, COL_SETSUMEI) else
        "empty"
    )


def classify_all_rows(cells: Sequence[Cell]) -> tuple[tuple[int, str], ...]:
    """Classify every row. Returns sorted (row_index, kind) pairs."""
    idx = build_cell_index(cells)
    headers = detect_header_rows(cells)
    return tuple(
        (r, classify_row(idx, r, headers))
        for r in all_rows(cells)
    )


# ---------------------------------------------------------------------------
# Grouping: by 目 (reduce-based, no mutation)
# ---------------------------------------------------------------------------

_MokuAcc = tuple[
    tuple[tuple[int | None, tuple[int, ...]], ...],
    int | None,
    tuple[int, ...],
]


def _moku_step(acc: _MokuAcc, item: tuple[int, str]) -> _MokuAcc:
    groups, cur_moku, cur_children = acc
    row, kind = item
    flushed = (
        (*groups, (cur_moku, cur_children))
        if cur_moku is not None or cur_children
        else groups
    )
    return (
        (flushed, row, ())
        if kind == "moku"
        else (groups, cur_moku, (*cur_children, row))
    )


def _finalize_moku(acc: _MokuAcc) -> tuple[tuple[int | None, tuple[int, ...]], ...]:
    groups, final_moku, final_children = acc
    return (
        (*groups, (final_moku, final_children))
        if final_moku is not None or final_children
        else groups
    )


def group_rows_by_moku(
    classified: Sequence[tuple[int, str]],
) -> tuple[tuple[int | None, tuple[int, ...]], ...]:
    """Group data rows by 目 anchor. Returns ((moku_row|None, child_rows), ...)."""
    data = tuple((r, k) for r, k in classified if k not in ("header", "empty"))
    return _finalize_moku(reduce(_moku_step, data, ((), None, ())))


# ---------------------------------------------------------------------------
# Grouping: by 節 within a 目's children (reduce-based)
# ---------------------------------------------------------------------------

_SetsuAcc = tuple[
    tuple[tuple[int | None, tuple[int, ...]], ...],
    int | None,
    tuple[int, ...],
]


def _make_setsu_step(idx: CellIndex):
    def step(acc: _SetsuAcc, row: int) -> _SetsuAcc:
        groups, cur_setsu, cur_children = acc
        flushed = (
            (*groups, (cur_setsu, cur_children))
            if cur_setsu is not None or cur_children
            else groups
        )
        return (
            (flushed, row, ())
            if _is_setsu(idx, row)
            else (groups, cur_setsu, (*cur_children, row))
        )
    return step


def _finalize_setsu(acc: _SetsuAcc) -> tuple[tuple[int | None, tuple[int, ...]], ...]:
    groups, final_setsu, final_children = acc
    return (
        (*groups, (final_setsu, final_children))
        if final_setsu is not None or final_children
        else groups
    )


def group_rows_by_setsu(
    idx: CellIndex,
    rows: Sequence[int],
) -> tuple[tuple[int | None, tuple[int, ...]], ...]:
    return _finalize_setsu(
        reduce(_make_setsu_step(idx), rows, ((), None, ()))
    )


# ---------------------------------------------------------------------------
# Name collection with continuation rows
# ---------------------------------------------------------------------------

def _continuation_rows(idx: CellIndex, rows: Sequence[int]) -> tuple[int, ...]:
    return tuple(takewhile(lambda r: _is_continuation(idx, r), rows))


def collect_full_name(idx: CellIndex, base_row: int, child_rows: Sequence[int]) -> str:
    base = text_at(idx, base_row, COL_KUBUN) or ""
    cont = _continuation_rows(idx, child_rows)
    return base + "".join(text_at(idx, r, COL_KUBUN) or "" for r in cont)


# ---------------------------------------------------------------------------
# Record assembly (pure)
# ---------------------------------------------------------------------------

def build_setsu_record(
    idx: CellIndex,
    setsu_row: int | None,
    child_rows: tuple[int, ...],
) -> SetsuRecord:
    full_name = (
        collect_full_name(idx, setsu_row, child_rows) if setsu_row is not None else ""
    )
    parsed = parse_setsu_text(full_name) if full_name else None
    number = parsed[0] if parsed else None
    name = parsed[1] if parsed else full_name
    amount = (
        parse_amount(text_at(idx, setsu_row, COL_KINGAKU) or "")
        if setsu_row is not None else None
    )

    skip = len(_continuation_rows(idx, child_rows)) if setsu_row is not None else 0
    effective = child_rows[skip:]

    sub_items = tuple(
        (text_at(idx, r, COL_KUBUN) or "", parse_amount(text_at(idx, r, COL_KINGAKU) or ""))
        for r in effective
        if _is_sub_item(idx, r)
    )

    setsumei_rows = (
        ((setsu_row,) if setsu_row is not None else ())
        + tuple(effective)
    )
    setsumei = tuple(
        parse_setsumei_line(t)
        for r in setsumei_rows
        if (t := text_at(idx, r, COL_SETSUMEI)) and t.strip()
    )

    return SetsuRecord(
        number=number, name=name, amount=amount,
        sub_items=sub_items, setsumei=setsumei,
    )


def build_moku_record(
    idx: CellIndex,
    moku_row: int,
    child_rows: tuple[int, ...],
) -> MokuRecord:
    right_rows = (
        (moku_row, *child_rows)
        if _has_text(idx, moku_row, COL_KUBUN) or _has_text(idx, moku_row, COL_SETSUMEI)
        else child_rows
    )

    setsu_groups = group_rows_by_setsu(idx, right_rows)
    setsu_list = tuple(
        build_setsu_record(idx, sr, cr)
        for sr, cr in setsu_groups
    )

    return MokuRecord(
        name=text_at(idx, moku_row, COL_MOKU) or "",
        honendo=parse_amount(text_at(idx, moku_row, COL_HONENDO) or ""),
        zenendo=parse_amount(text_at(idx, moku_row, COL_ZENENDO) or ""),
        hikaku=parse_amount(text_at(idx, moku_row, COL_HIKAKU) or ""),
        zaigen=Zaigen(
            kokuken=parse_amount(text_at(idx, moku_row, COL_KOKUKEN) or ""),
            chihousei=parse_amount(text_at(idx, moku_row, COL_CHIHOUSEI) or ""),
            sonota=parse_amount(text_at(idx, moku_row, COL_SONOTA) or ""),
            ippan=parse_amount(text_at(idx, moku_row, COL_IPPAN) or ""),
        ),
        setsu_list=setsu_list,
    )


# ---------------------------------------------------------------------------
# Top-level composition
# ---------------------------------------------------------------------------

def parse_page_budget(cells: Sequence[Cell]) -> PageBudget:
    """Top-level pure function: cells → structured budget data."""
    idx = build_cell_index(cells)
    classified = classify_all_rows(cells)
    moku_groups = group_rows_by_moku(classified)

    moku_records = tuple(
        build_moku_record(idx, moku_row, children)
        for moku_row, children in moku_groups
        if moku_row is not None
    )

    orphan_setsu = tuple(
        build_setsu_record(idx, sr, cr)
        for moku_row, children in moku_groups
        if moku_row is None
        for sr, cr in group_rows_by_setsu(idx, children)
    )

    return PageBudget(moku_records=moku_records, orphan_setsu=orphan_setsu)

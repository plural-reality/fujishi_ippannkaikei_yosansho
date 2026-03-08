"""
Pure budget parsing: Cell[] → PageBudget.

Pipeline (all pure, composable):
  tuple[Cell, ...] → CellIndex → classify_all_rows → group_rows_by_moku
    → group_rows_by_setsu → build records → PageBudget

No IO. Depends only on types.
"""

from __future__ import annotations

import re
from dataclasses import replace
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
    Word,
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


# ---------------------------------------------------------------------------
# Coordinate-based setsumei parsing (replaces regex-based parse_setsumei_line)
# ---------------------------------------------------------------------------

_AMOUNT_MARGIN = 50.0   # words within this distance of cell right edge → amount
_CODE_MARGIN = 25.0     # words within this distance of cell left edge + 3-digit → code
_LINE_Y_TOLERANCE = 1.2  # same logical line if y-center distance <= this value
_CODE_RE = re.compile(r"^\d{3}$")
_AMOUNT_RE = re.compile(r"^[\d,△\-]+$")


def _is_amount_word(w: Word, cell_x1: float) -> bool:
    """Word is near cell right edge and looks like a number."""
    return cell_x1 - w.x1 < _AMOUNT_MARGIN and bool(_AMOUNT_RE.match(w.text))


def _is_code_word(w: Word, cell_x0: float) -> bool:
    """Word is near cell left edge and is a 3-digit code."""
    return w.x0 - cell_x0 < _CODE_MARGIN and bool(_CODE_RE.match(w.text))


def parse_setsumei_cell(cell: Cell) -> SetsumeiEntry:
    """Parse a setsumei cell using word coordinates.

    Layout in the 説明 column:
      [code]  [name ...]  [amount]
       left     middle      right-aligned

    Coordinate-based separation is strictly more robust than regex.
    """
    words = cell.words
    return (
        SetsumeiEntry("text", None, "", None)
        if not words
        else _parse_setsumei_from_words(words, cell.x0, cell.x1)
    )


def _parse_setsumei_from_words(
    words: tuple[Word, ...], cell_x0: float, cell_x1: float,
) -> SetsumeiEntry:
    amount_ws = tuple(w for w in words if _is_amount_word(w, cell_x1))
    code_ws = tuple(w for w in words if _is_code_word(w, cell_x0))
    name_ws = tuple(w for w in words if w not in amount_ws and w not in code_ws)

    code = code_ws[0].text if code_ws else None
    name = " ".join(w.text for w in name_ws)
    amount = parse_amount(" ".join(w.text for w in amount_ws)) if amount_ws else None

    return SetsumeiEntry(
        kind="coded" if code else "text",
        code=code,
        name=name,
        amount=amount,
    )


def _word_mid_y(word: Word) -> float:
    return (word.y0 + word.y1) / 2.0


_LineClusterAcc = tuple[tuple[tuple[Word, ...], ...], tuple[Word, ...], float | None]


def _line_cluster_step(acc: _LineClusterAcc, word: Word) -> _LineClusterAcc:
    lines, cur_words, cur_y = acc
    y = _word_mid_y(word)
    return (
        (lines, (word,), y)
        if not cur_words
        else (
            (lines, (*cur_words, word), (((cur_y or y) * len(cur_words)) + y) / (len(cur_words) + 1))
            if cur_y is not None and abs(y - cur_y) <= _LINE_Y_TOLERANCE
            else ((*lines, tuple(sorted(cur_words, key=lambda w: w.x0))), (word,), y)
        )
    )


def _finalize_line_clusters(acc: _LineClusterAcc) -> tuple[tuple[Word, ...], ...]:
    lines, cur_words, _ = acc
    return (
        (*lines, tuple(sorted(cur_words, key=lambda w: w.x0)))
        if cur_words
        else lines
    )


def split_words_into_lines(words: Sequence[Word]) -> tuple[tuple[Word, ...], ...]:
    """Cluster words into logical lines by y-position, then sort each line by x."""
    sorted_words = tuple(sorted(words, key=lambda w: (_word_mid_y(w), w.x0)))
    return _finalize_line_clusters(
        reduce(_line_cluster_step, sorted_words, ((), (), None))
    )


def _parse_setsumei_line(
    words: tuple[Word, ...], cell_x0: float, cell_x1: float,
) -> tuple[SetsumeiEntry, bool]:
    """Parse one logical line. bool indicates whether the line has right-edge amount."""
    amount_ws = tuple(w for w in words if _is_amount_word(w, cell_x1))
    code_ws = tuple(w for w in words if _is_code_word(w, cell_x0))
    name_ws = tuple(w for w in words if w not in amount_ws and w not in code_ws)

    code = code_ws[0].text if code_ws else None
    amount = parse_amount(" ".join(w.text for w in amount_ws)) if amount_ws else None
    entry = SetsumeiEntry(
        kind="coded" if code else "text",
        code=code,
        name=" ".join(w.text for w in name_ws),
        amount=amount,
    )
    return (entry, bool(amount_ws))


def parse_setsumei_cell_lines(cell: Cell) -> tuple[tuple[SetsumeiEntry, bool], ...]:
    """Parse one setsumei cell into logical line entries with amount-anchor flag."""
    return tuple(
        _parse_setsumei_line(line_words, cell.x0, cell.x1)
        for line_words in split_words_into_lines(cell.words)
    )


def _join_text(base: str, extra: str) -> str:
    return (
        extra
        if not base
        else base
        if not extra
        else f"{base} {extra}"
    )


def _merge_supplement_line(base: SetsumeiEntry, supplement: SetsumeiEntry) -> SetsumeiEntry:
    """Attach a non-amount supplement line to a base entry."""
    merged_code = base.code or supplement.code
    return replace(
        base,
        kind="coded" if merged_code else "text",
        code=merged_code,
        name=_join_text(base.name, supplement.name),
        amount=base.amount if base.amount is not None else supplement.amount,
    )


def fold_setsumei_lines(
    line_entries: Sequence[tuple[SetsumeiEntry, bool]],
) -> tuple[SetsumeiEntry, ...]:
    """Fold line-level entries into logical setsumei entries.

    Rule:
      - amount line: starts a new entry
      - non-amount line: attaches to the previous entry as supplement
      - if there is no previous entry, keep it as a standalone entry
    """
    def step(
        acc: tuple[SetsumeiEntry, ...],
        item: tuple[SetsumeiEntry, bool],
    ) -> tuple[SetsumeiEntry, ...]:
        entry, has_amount = item
        return (
            (*acc, entry)
            if has_amount or not acc
            else (*acc[:-1], _merge_supplement_line(acc[-1], entry))
        )

    return reduce(step, line_entries, ())


def parse_setsumei_cells(cells: Sequence[Cell]) -> tuple[SetsumeiEntry, ...]:
    """Parse and fold all setsumei cells of one setsu in row order."""
    lines = tuple(
        line
        for cell in cells
        for line in parse_setsumei_cell_lines(cell)
    )
    return fold_setsumei_lines(lines)


# ---------------------------------------------------------------------------
# Cell index (immutable lookup) — now stores Cell objects
# ---------------------------------------------------------------------------

CellIndex = Mapping[tuple[int, int], Cell]


def build_cell_index(cells: Sequence[Cell]) -> CellIndex:
    """Immutable (row, col) → Cell mapping."""
    return MappingProxyType({(c.row, c.col): c for c in cells})


def cell_at(idx: CellIndex, row: int, col: int) -> Cell | None:
    """Lookup cell. None if absent."""
    return idx.get((row, col))


def text_at(idx: CellIndex, row: int, col: int) -> str | None:
    """Lookup cell text. None if absent."""
    c = idx.get((row, col))
    return c.text if c is not None else None


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
        _normalize(v.text) for (r, _), v in idx.items() if r == row
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

    # Collect setsumei using coordinate-based parsing
    setsumei_rows = (
        ((setsu_row,) if setsu_row is not None else ())
        + tuple(effective)
    )
    setsumei_cells = tuple(
        cell
        for r in setsumei_rows
        if (cell := cell_at(idx, r, COL_SETSUMEI)) is not None and cell.text.strip()
    )
    setsumei = parse_setsumei_cells(setsumei_cells)

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

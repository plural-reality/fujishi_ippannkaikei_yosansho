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

_LINE_Y_TOLERANCE = 1.2  # same logical line if y-center distance <= this value
_MERGE_Y_TOLERANCE = 1.0  # merge consecutive lines if y-gap <= this value
_INDENT_NOISE = 2.5
_CODE_TO_NAME_OFFSET_DEFAULT = 14.0
_CODE_RE = re.compile(r"^\d{3}$")
_AMOUNT_RE = re.compile(r"^[\d,△]+$")  # digits, commas, triangle only (no text like "1人")


def _is_code(text: str) -> bool:
    """Check if text is a 3-digit code."""
    return bool(_CODE_RE.match(text))


def _is_amount(text: str) -> bool:
    """Check if text is a pure amount (digits and commas only, no text)."""
    return bool(_AMOUNT_RE.match(text))


def parse_setsumei_cell(cell: Cell) -> SetsumeiEntry:
    """Parse a setsumei cell using word coordinates.

    Layout in the 説明 column:
      [code]  [name ...]  [amount]
       left     middle      right-aligned

    Words are processed left-to-right:
    - First word: code if 3-digit, else name
    - Last word: amount if digits+commas only, else name
    - Middle words: name
    """
    words = cell.words
    return (
        SetsumeiEntry("text", None, "", None)
        if not words
        else _parse_setsumei_from_words(words)
    )


def _parse_setsumei_from_words(words: tuple[Word, ...]) -> SetsumeiEntry:
    """Parse words left-to-right: [code?] [name...] [amount?]."""
    sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))

    if not sorted_words:
        return SetsumeiEntry("text", None, "", None)

    # Check for code at the very first position
    code = None
    if _is_code(sorted_words[0].text):
        code = sorted_words[0].text
        sorted_words = sorted_words[1:]

    if not sorted_words:
        return SetsumeiEntry("coded" if code else "text", code, "", None)

    # Check for amount at the very last position
    amount = None
    if _is_amount(sorted_words[-1].text):
        amount = parse_amount(sorted_words[-1].text)
        sorted_words = sorted_words[:-1]

    # Validate: no code should appear except at the first position
    for w in sorted_words:
        if _is_code(w.text):
            raise ValueError(
                f"Unexpected code '{w.text}' found in middle of setsumei. "
                f"Code must be at the first position only. Words: {[w.text for w in words]}"
            )

    # Remaining words are name
    name = " ".join(w.text for w in sorted_words)

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
    words: tuple[Word, ...],
) -> tuple[SetsumeiEntry, bool, float | None, float | None]:
    """Parse one logical line left-to-right.

    Returns:
      - entry
      - has_amount (last word is numeric)
      - code_x (left x of code token, if any)
      - name_x (left x of first name token, if any)
    """
    sorted_words = list(sorted(words, key=lambda w: w.x0))

    if not sorted_words:
        return (SetsumeiEntry("text", None, "", None), False, None, None)

    # Code at first position only
    code = None
    code_x = None
    if _is_code(sorted_words[0].text):
        code = sorted_words[0].text
        code_x = sorted_words[0].x0
        sorted_words = sorted_words[1:]

    if not sorted_words:
        return (SetsumeiEntry("coded" if code else "text", code, "", None), False, code_x, None)

    # Amount at last position only
    amount = None
    has_amount = False
    if _is_amount(sorted_words[-1].text):
        amount = parse_amount(sorted_words[-1].text)
        has_amount = True
        sorted_words = sorted_words[:-1]

    # Remaining words are name
    name_x = sorted_words[0].x0 if sorted_words else None
    name = " ".join(w.text for w in sorted_words)

    entry = SetsumeiEntry(
        kind="coded" if code else "text",
        code=code,
        name=name,
        amount=amount,
    )
    return (entry, has_amount, code_x, name_x)


def _line_bottom_y(words: tuple[Word, ...]) -> float:
    """Get the bottom y-coordinate of a line."""
    return max(w.y1 for w in words) if words else 0.0


def _line_top_y(words: tuple[Word, ...]) -> float:
    """Get the top y-coordinate of a line."""
    return min(w.y0 for w in words) if words else 0.0


def _merge_close_lines(
    lines: tuple[tuple[Word, ...], ...],
) -> tuple[tuple[Word, ...], ...]:
    """Merge consecutive lines if y-gap <= _MERGE_Y_TOLERANCE (1pt).

    Lines with gap <= 1pt are considered "two lines forming one entry".
    """
    if not lines:
        return ()

    merged: list[tuple[Word, ...]] = []
    current_words: list[Word] = list(lines[0])
    current_bottom = _line_bottom_y(lines[0])

    for line in lines[1:]:
        line_top = _line_top_y(line)
        gap = line_top - current_bottom

        if gap <= _MERGE_Y_TOLERANCE:
            # Merge: add words to current group
            current_words.extend(line)
            current_bottom = max(current_bottom, _line_bottom_y(line))
        else:
            # New group
            merged.append(tuple(sorted(current_words, key=lambda w: (w.y0, w.x0))))
            current_words = list(line)
            current_bottom = _line_bottom_y(line)

    # Finalize last group
    merged.append(tuple(sorted(current_words, key=lambda w: (w.y0, w.x0))))

    return tuple(merged)


def parse_setsumei_cell_lines(
    cell: Cell,
) -> tuple[tuple[SetsumeiEntry, bool, float | None, float | None], ...]:
    """Parse one setsumei cell into logical line entries with amount-anchor flag.

    Lines within 1pt y-gap are merged into a single entry.
    """
    raw_lines = split_words_into_lines(cell.words)
    merged_lines = _merge_close_lines(raw_lines)
    return tuple(
        _parse_setsumei_line(line_words)
        for line_words in merged_lines
    )


def _apply_level(entry: SetsumeiEntry, level: int) -> SetsumeiEntry:
    """Attach 1-based hierarchical level to entry without mutating text."""
    return replace(entry, level=level)


def _cluster_left_positions(values: Sequence[float], tol: float) -> tuple[float, ...]:
    if not values:
        return ()
    sorted_values = tuple(sorted(values))
    clusters: tuple[tuple[float, int], ...] = ()
    for v in sorted_values:
        clusters = (
            ((v, 1),)
            if not clusters
            else (
                (*clusters[:-1], (((clusters[-1][0] * clusters[-1][1]) + v) / (clusters[-1][1] + 1), clusters[-1][1] + 1))
                if abs(v - clusters[-1][0]) <= tol
                else (*clusters, (v, 1))
            )
        )
    return tuple(center for center, _ in clusters)


def _resolve_level_anchors(
    line_entries: Sequence[tuple[SetsumeiEntry, bool, float | None, float | None]],
) -> tuple[float, tuple[float, ...]]:
    code_name_offsets = tuple(
        name_x - code_x
        for _, _, code_x, name_x in line_entries
        if code_x is not None and name_x is not None and name_x >= code_x
    )
    code_to_name_offset = (
        min(code_name_offsets)
        if code_name_offsets
        else _CODE_TO_NAME_OFFSET_DEFAULT
    )

    def normalized_left(code_x: float | None, name_x: float | None) -> float | None:
        return (
            code_x
            if code_x is not None
            else (name_x - code_to_name_offset if name_x is not None else None)
        )

    anchor_lefts = tuple(
        left
        for _, has_amount, code_x, name_x in line_entries
        for left in (normalized_left(code_x, name_x),)
        if left is not None and (code_x is not None or has_amount)
    )
    fallback_lefts = tuple(
        left
        for _, _, code_x, name_x in line_entries
        for left in (normalized_left(code_x, name_x),)
        if left is not None
    )
    anchors = _cluster_left_positions(
        anchor_lefts if anchor_lefts else fallback_lefts,
        _INDENT_NOISE,
    )
    return (
        code_to_name_offset,
        anchors if anchors else (0.0,),
    )


def _nearest_level(left: float | None, anchors: Sequence[float]) -> int:
    if left is None:
        return 1
    nearest = min(
        range(len(anchors)),
        key=lambda i: abs(left - anchors[i]),
    )
    return nearest + 1


def fold_setsumei_lines(
    line_entries: Sequence[tuple[SetsumeiEntry, bool, float | None, float | None]],
) -> tuple[SetsumeiEntry, ...]:
    """Convert line-level entries into semantic entries with hierarchical level."""
    code_to_name_offset, anchors = _resolve_level_anchors(line_entries)

    def normalized_left(code_x: float | None, name_x: float | None) -> float | None:
        return (
            code_x
            if code_x is not None
            else (name_x - code_to_name_offset if name_x is not None else None)
        )

    return tuple(
        _apply_level(entry, _nearest_level(normalized_left(code_x, name_x), anchors))
        for entry, _, code_x, name_x in line_entries
    )


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

def _collect_setsumei_cells(
    idx: CellIndex,
    setsu_row: int | None,
    child_rows: tuple[int, ...],
) -> tuple[Cell, ...]:
    """Collect setsumei cells for one setsu group (rows only, no level resolution)."""
    skip = len(_continuation_rows(idx, child_rows)) if setsu_row is not None else 0
    effective = child_rows[skip:]
    setsumei_rows = (
        ((setsu_row,) if setsu_row is not None else ())
        + tuple(effective)
    )
    return tuple(
        cell
        for r in setsumei_rows
        if (cell := cell_at(idx, r, COL_SETSUMEI)) is not None and cell.text.strip()
    )


def _fold_setsumei_with_anchors(
    cells: Sequence[Cell],
    anchors: tuple[float, ...],
    code_to_name_offset: float,
) -> tuple[SetsumeiEntry, ...]:
    """Fold setsumei cells using pre-computed moku-level anchors."""
    lines = tuple(
        line
        for cell in cells
        for line in parse_setsumei_cell_lines(cell)
    )

    def normalized_left(code_x: float | None, name_x: float | None) -> float | None:
        return (
            code_x
            if code_x is not None
            else (name_x - code_to_name_offset if name_x is not None else None)
        )

    return tuple(
        _apply_level(entry, _nearest_level(normalized_left(code_x, name_x), anchors))
        for entry, _, code_x, name_x in lines
    )


def build_setsu_record(
    idx: CellIndex,
    setsu_row: int | None,
    child_rows: tuple[int, ...],
    moku_anchors: tuple[float, ...] | None = None,
    moku_code_to_name_offset: float | None = None,
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

    setsumei_cells = _collect_setsumei_cells(idx, setsu_row, child_rows)
    setsumei = (
        _fold_setsumei_with_anchors(setsumei_cells, moku_anchors, moku_code_to_name_offset)
        if moku_anchors is not None and moku_code_to_name_offset is not None
        else parse_setsumei_cells(setsumei_cells)
    )

    return SetsuRecord(
        number=number, name=name, amount=amount,
        sub_items=sub_items, setsumei=setsumei,
    )


def _moku_level_anchors(
    idx: CellIndex,
    setsu_groups: Sequence[tuple[int | None, tuple[int, ...]]],
) -> tuple[float, tuple[float, ...]]:
    """Compute setsumei level anchors across all setsu in one moku.

    説明 is 1:1 with 目 — indent anchors must be resolved at moku scope,
    not per-setsu, to avoid context fragmentation across 節 boundaries.
    """
    all_lines = tuple(
        line
        for sr, cr in setsu_groups
        for cell in _collect_setsumei_cells(idx, sr, cr)
        for line in parse_setsumei_cell_lines(cell)
    )
    return _resolve_level_anchors(all_lines)


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

    # Resolve setsumei anchors at moku level (説明 is 1:1 with 目)
    code_to_name_offset, anchors = _moku_level_anchors(idx, setsu_groups)

    setsu_list = tuple(
        build_setsu_record(idx, sr, cr, moku_anchors=anchors, moku_code_to_name_offset=code_to_name_offset)
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

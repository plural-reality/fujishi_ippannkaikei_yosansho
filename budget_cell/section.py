"""
Pure mid-page section split driven by cell-layer 款/項 markers.

A page can contain repeated page-top headers and mid-page transitions where
new 款/項 labels are rendered inside table cells instead of above the grid.
This module removes those meta rows and splits cells into (PageHeader, cells)
segments using the cell layer as the source of truth.

Depends only on types + re. No IO.
"""

from __future__ import annotations

import re
from functools import reduce
from typing import Mapping, Sequence

from budget_cell.types import Cell, PageHeader


_SUBTOTAL_RE = re.compile(r"^計\s*")
_KAN_RE = re.compile(r"([０-９\d]+)\s*款")
_KOU_RE = re.compile(r"([０-９\d]+)\s*項")
_HEADER_TOKENS = frozenset({
    "目", "千円", "節", "本年度予算額", "前年度予算額",
    "一般財源", "国県支出金", "地方債", "その他",
    "区分", "金額", "説明", "比較", "歳出",
})

_HeaderUpdate = tuple[str, str, str, str]

COL_MOKU = 0


def _normalize(value: str) -> str:
    return value.strip().replace(" ", "").replace("\n", "").replace("\u3000", "")


def _unique_rows(cells: Sequence[Cell]) -> tuple[int, ...]:
    return tuple(sorted({c.row for c in cells}))


def _row_cells(cells: Sequence[Cell]) -> Mapping[int, tuple[Cell, ...]]:
    rows = _unique_rows(cells)
    return {
        row: tuple(sorted((c for c in cells if c.row == row), key=lambda c: c.col))
        for row in rows
    }


def _cell_text(row_cells: Sequence[Cell], col: int) -> str:
    return next((c.text.strip() for c in row_cells if c.col == col), "")


def _candidate_name(text: str) -> str:
    normalized = _normalize(text)
    return (
        ""
        if not normalized
        or bool(_KAN_RE.search(normalized))
        or bool(_KOU_RE.search(normalized))
        or normalized in _HEADER_TOKENS
        else normalized
    )


def _extract_tag(
    row_cells: Sequence[Cell],
    pattern: re.Pattern[str],
    other_pattern: re.Pattern[str],
    allow_next_after_other: bool,
) -> tuple[str, str] | None:
    normalized_cells = tuple(_normalize(cell.text) for cell in row_cells)

    def next_name(index: int) -> str:
        return (
            _candidate_name(row_cells[index + 1].text)
            if index + 1 < len(row_cells)
            else ""
        )

    def joined_match() -> tuple[str, str] | None:
        return next(
            (
                (
                    match.group(1),
                    suffix
                    if suffix
                    else (
                        _candidate_name(row_cells[end].text)
                        if end < len(row_cells) and (
                            allow_next_after_other or not bool(other_pattern.search(joined))
                        )
                        else ""
                    ),
                )
                for start in range(len(normalized_cells))
                for end in range(start + 2, min(start + 4, len(normalized_cells)) + 1)
                for joined in ("".join(normalized_cells[start:end]),)
                for match in (pattern.search(joined),)
                if match is not None
                for suffix in (_candidate_name(joined[match.end():]),)
            ),
            None,
        )

    tagged = next(
        (
            (index, cell, found[-1])
            for index, cell in enumerate(row_cells)
            for found in (tuple(pattern.finditer(_normalize(cell.text))),)
            if found
        ),
        None,
    )
    if tagged is None:
        return joined_match()

    index, cell, match = tagged
    normalized = _normalize(cell.text)
    suffix = _candidate_name(normalized[match.end():])
    allow_next = allow_next_after_other or not bool(other_pattern.search(normalized))
    name = suffix if suffix else next_name(index) if allow_next else ""
    return (match.group(1), name)


def _extract_row_update(row_cells: Sequence[Cell]) -> _HeaderUpdate:
    kan = _extract_tag(row_cells, _KAN_RE, _KOU_RE, True)
    kou = _extract_tag(row_cells, _KOU_RE, _KAN_RE, False)
    return (
        kan[0] if kan is not None else "",
        kan[1] if kan is not None else "",
        kou[0] if kou is not None else "",
        kou[1] if kou is not None else "",
    )


def _has_update(update: _HeaderUpdate) -> bool:
    return any(update)


def _merge_header(base: PageHeader, update: _HeaderUpdate) -> PageHeader:
    kan_number, kan_name, kou_number, kou_name = update
    return PageHeader(
        kan_number=kan_number or base.kan_number,
        kan_name=kan_name or base.kan_name,
        kou_number=kou_number or base.kou_number,
        kou_name=kou_name or base.kou_name,
    )


def _is_subtotal_row(row_cells: Sequence[Cell]) -> bool:
    return bool(_SUBTOTAL_RE.match(_cell_text(row_cells, COL_MOKU)))


def _is_table_header_row(row_cells: Sequence[Cell]) -> bool:
    texts = frozenset(_normalize(cell.text) for cell in row_cells if _normalize(cell.text))
    return bool(texts & _HEADER_TOKENS)


def _cells_in_rows(cells: Sequence[Cell], rows: frozenset[int]) -> tuple[Cell, ...]:
    return tuple(c for c in cells if c.row in rows)


def split_page_sections(
    header: PageHeader,
    cells: Sequence[Cell],
) -> tuple[tuple[PageHeader, tuple[Cell, ...]], ...]:
    rows = _unique_rows(cells)
    by_row = _row_cells(cells)

    def step(
        acc: tuple[
            tuple[tuple[PageHeader, frozenset[int]], ...],
            PageHeader,
            PageHeader,
            frozenset[int],
        ],
        row: int,
    ) -> tuple[
        tuple[tuple[PageHeader, frozenset[int]], ...],
        PageHeader,
        PageHeader,
        frozenset[int],
    ]:
        segments, current_header, pending_header, current_rows = acc
        row_cells = by_row[row]
        update = _extract_row_update(row_cells)
        is_meta = (
            _is_subtotal_row(row_cells)
            or _is_table_header_row(row_cells)
            or _has_update(update)
        )
        next_pending = _merge_header(pending_header, update) if _has_update(update) else pending_header
        should_split = bool(current_rows) and next_pending != current_header and not is_meta
        next_segments = (
            (*segments, (current_header, current_rows))
            if should_split
            else segments
        )
        next_current_header = (
            next_pending
            if not current_rows or should_split
            else current_header
        )
        next_rows = (
            current_rows
            if is_meta
            else (
                frozenset((row,))
                if should_split or not current_rows
                else frozenset((*current_rows, row))
            )
        )
        return (next_segments, next_current_header, next_pending, next_rows)

    segments, current_header, _, current_rows = (
        ((), header, header, frozenset())
        if not rows
        else reduce(step, rows, ((), header, header, frozenset()))
    )

    finalized = (
        (*segments, (current_header, current_rows))
        if current_rows
        else segments
    )

    return tuple(
        (segment_header, _cells_in_rows(cells, segment_rows))
        for segment_header, segment_rows in finalized
        if segment_rows
    )

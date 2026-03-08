"""
Year-over-year trend representation from Excel-derived FlatRow streams.

This module is intentionally decoupled from PDF extraction.
Input contract: FlatRow sequence only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping, Sequence

from budget_cell.types import FlatRow


@dataclass(frozen=True)
class TrendKey:
    kan_name: str
    kou_name: str
    moku_name: str
    path_levels: tuple[str, ...]


@dataclass(frozen=True)
class TrendNode:
    year: str
    key: TrendKey
    setsu_number: int | None
    setsu_name: str
    setsumei_code: str
    setsumei_level: int
    setsumei_name: str
    amount: int


@dataclass(frozen=True)
class TrendRow:
    key: TrendKey
    year_amounts: tuple[int, ...]
    diff: int
    ratio: float | None
    status: str


def _year_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", value)
    return ((int(match.group(1)) if match else 10_000), value)


def _clean_text(value: str) -> str:
    return value.strip()


def _level_or_default(value: int | None) -> int:
    return value if value and value > 0 else 1


def _advance_path(
    previous: tuple[str, ...],
    level: int,
    name: str,
) -> tuple[str, ...]:
    size = max(len(previous), level)
    padded = tuple(
        previous[idx] if idx < len(previous) else ""
        for idx in range(size)
    )
    return tuple(
        name if idx == level - 1 else padded[idx] if idx < level - 1 else ""
        for idx in range(size)
    )


def _path_from_levels(levels: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item for item in levels if item)


def rows_to_trend_nodes(
    year: str,
    rows: Sequence[FlatRow],
) -> tuple[TrendNode, ...]:
    path_state: dict[tuple[str, str, str, int | None, str, str], tuple[str, ...]] = {}
    result: list[TrendNode] = []
    for row in rows:
        name = _clean_text(row.setsumei_name)
        level = _level_or_default(row.setsumei_level)
        context_key = (
            _clean_text(row.kan_name),
            _clean_text(row.kou_name),
            _clean_text(row.moku_name),
            row.setsu_number,
            _clean_text(row.setsu_name),
            _clean_text(row.setsumei_code),
        )
        next_levels = (
            _advance_path(path_state.get(context_key, ()), level, name)
            if name
            else path_state.get(context_key, ())
        )
        path_state[context_key] = next_levels
        amount = row.setsumei_amount
        result.append(
            TrendNode(
                year=year,
                key=TrendKey(
                    kan_name=context_key[0],
                    kou_name=context_key[1],
                    moku_name=context_key[2],
                    path_levels=_path_from_levels(next_levels),
                ),
                setsu_number=row.setsu_number,
                setsu_name=context_key[4],
                setsumei_code=context_key[5],
                setsumei_level=level,
                setsumei_name=name,
                amount=amount if amount is not None else 0,
            )
        ) if name and amount is not None else None
    return tuple(result)


def _status(base: int, latest: int) -> str:
    return (
        "新規"
        if base == 0 and latest != 0
        else "廃止"
        if base != 0 and latest == 0
        else "増額"
        if latest > base
        else "減額"
        if latest < base
        else "横ばい"
    )


def _ratio(base: int, diff: int) -> float | None:
    return None if base == 0 else diff / base


def aggregate_trends(
    nodes: Sequence[TrendNode],
) -> tuple[tuple[str, ...], tuple[TrendRow, ...]]:
    years = tuple(sorted({node.year for node in nodes}, key=_year_sort_key))
    key_year_sum: dict[tuple[TrendKey, str], int] = {}
    for node in nodes:
        index = (node.key, node.year)
        key_year_sum[index] = key_year_sum.get(index, 0) + node.amount

    keys = tuple(
        sorted(
            {key for key, _ in key_year_sum.keys()},
            key=lambda key: (
                key.kan_name,
                key.kou_name,
                key.moku_name,
                key.path_levels,
            ),
        )
    )
    rows = tuple(
        (
            lambda amounts: TrendRow(
                key=key,
                year_amounts=amounts,
                diff=amounts[-1] - amounts[0],
                ratio=_ratio(amounts[0], amounts[-1] - amounts[0]),
                status=_status(amounts[0], amounts[-1]),
            )
        )(tuple(key_year_sum.get((key, year), 0) for year in years))
        for key in keys
    )
    ranked = tuple(
        sorted(
            rows,
            key=lambda row: (abs(row.diff), row.key.kou_name, row.key.moku_name, row.key.path_levels),
            reverse=True,
        )
    )
    return years, ranked


def _max_path_depth(rows: Sequence[TrendRow]) -> int:
    return max((len(row.key.path_levels) for row in rows), default=1)


def _base_headers(depth: int) -> tuple[str, ...]:
    return ("款", "項", "目", *(f"説明L{i}" for i in range(1, depth + 1)))


def _sheet_row(
    row: TrendRow,
    depth: int,
    rank: int | None = None,
) -> tuple:
    levels = tuple(
        row.key.path_levels[idx] if idx < len(row.key.path_levels) else ""
        for idx in range(depth)
    )
    return (
        row.key.kan_name,
        row.key.kou_name,
        row.key.moku_name,
        *levels,
        *row.year_amounts,
        row.diff,
        row.ratio if row.ratio is not None else "",
        row.status,
        rank if rank is not None else "",
    )


def write_trend_excel(
    dst_path: str,
    nodes: Sequence[TrendNode],
    top_n: int = 200,
) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    years, rows = aggregate_trends(nodes)
    depth = _max_path_depth(rows)
    headers = (*_base_headers(depth), *years, "増減額", "増減率", "状態", "増減額順位")

    workbook = openpyxl.Workbook()
    sheet_changes = workbook.active
    sheet_changes.title = "changes"
    sheet_short = workbook.create_sheet("short")
    sheet_up = workbook.create_sheet("top_up")
    sheet_down = workbook.create_sheet("top_down")
    sheet_raw = workbook.create_sheet("raw")

    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="DAEEF3", end_color="DAEEF3", fill_type="solid")

    def write_header(sheet, labels: Sequence[str]) -> None:
        for ci, label in enumerate(labels, 1):
            cell = sheet.cell(row=1, column=ci, value=label)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

    write_header(sheet_changes, headers)
    for ri, row in enumerate(rows, 2):
        values = _sheet_row(row, depth, rank=ri - 1)
        for ci, value in enumerate(values, 1):
            sheet_changes.cell(row=ri, column=ci, value=value)

    short_rows = rows[:top_n]
    write_header(sheet_short, headers)
    for ri, row in enumerate(short_rows, 2):
        values = _sheet_row(row, depth, rank=ri - 1)
        for ci, value in enumerate(values, 1):
            sheet_short.cell(row=ri, column=ci, value=value)

    top_up_rows = tuple(row for row in rows if row.diff > 0)[:top_n]
    top_down_rows = tuple(row for row in rows if row.diff < 0)[:top_n]

    write_header(sheet_up, headers)
    for ri, row in enumerate(top_up_rows, 2):
        values = _sheet_row(row, depth, rank=ri - 1)
        for ci, value in enumerate(values, 1):
            sheet_up.cell(row=ri, column=ci, value=value)

    write_header(sheet_down, headers)
    for ri, row in enumerate(top_down_rows, 2):
        values = _sheet_row(row, depth, rank=ri - 1)
        for ci, value in enumerate(values, 1):
            sheet_down.cell(row=ri, column=ci, value=value)

    raw_headers = (
        "年度", "款", "項", "目", "説明レベル", "説明", "説明パス", "説明金額",
        "節番号", "節名", "事業コード",
    )
    write_header(sheet_raw, raw_headers)
    for ri, node in enumerate(nodes, 2):
        values = (
            node.year,
            node.key.kan_name,
            node.key.kou_name,
            node.key.moku_name,
            node.setsumei_level,
            node.setsumei_name,
            " > ".join(node.key.path_levels),
            node.amount,
            node.setsu_number if node.setsu_number is not None else "",
            node.setsu_name,
            node.setsumei_code,
        )
        for ci, value in enumerate(values, 1):
            sheet_raw.cell(row=ri, column=ci, value=value)

    ratio_col = len(headers) - 2
    for sheet in (sheet_changes, sheet_short, sheet_up, sheet_down):
        for ri in range(2, sheet.max_row + 1):
            cell = sheet.cell(row=ri, column=ratio_col)
            cell.number_format = "0.0%"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.freeze_panes = "A2"

    sheet_raw.auto_filter.ref = sheet_raw.dimensions
    sheet_raw.freeze_panes = "A2"
    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
    workbook.save(dst_path)


def load_year_excel_nodes(
    year_to_path: Mapping[str, str],
    read_rows_fn,
) -> tuple[TrendNode, ...]:
    return tuple(
        node
        for year, path in year_to_path.items()
        for node in rows_to_trend_nodes(year, read_rows_fn(path))
    )

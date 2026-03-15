"""
Composable PDF extraction pipeline.

This module exposes pure data-pipeline style building blocks:
  PDF path -> section cells -> section rows -> labeled FlatRow stream.
"""

from __future__ import annotations

from itertools import groupby
from typing import Callable, Sequence

from budget_cell.cells import assign_words_to_cells
from budget_cell.extract import extract_all_geometries
from budget_cell.flatten import assign_setsumei_paths, flatten_all_pages, ffill, label_section
from budget_cell.geometry_normalize import normalize_page_geometries
from budget_cell.grid import build_grid, extract_expenditure_pages
from budget_cell.header import parse_page_header
from budget_cell.merge import merge_rows
from budget_cell.parse import parse_page_budget
from budget_cell.section import split_page_sections
from budget_cell.types import Cell, FlatRow, PageHeader


Logger = Callable[[str], None]
SectionCells = tuple[PageHeader, tuple[tuple[Cell, ...], ...]]
SectionRows = tuple[PageHeader, tuple[FlatRow, ...]]


def _log(logger: Logger | None, message: str) -> None:
    _ = logger(message) if logger is not None else None


def collect_section_cells(
    src_path: str,
    logger: Logger | None = None,
) -> tuple[SectionCells, ...]:
    _log(logger, f"Extracting geometries from {src_path}...")
    all_geoms = normalize_page_geometries(extract_all_geometries(src_path))
    _log(logger, f"  {len(all_geoms)} pages total")

    geoms = extract_expenditure_pages(all_geoms)
    _log(logger, f"  {len(geoms)} expenditure pages (after 歳出 title page)")

    _log(logger, "Building grids + extracting headers...")
    grids = tuple(map(build_grid, geoms))
    headers = tuple(parse_page_header(g, gr) for g, gr in zip(geoms, grids))

    valid = tuple(
        (h, g, gr)
        for h, g, gr in zip(headers, geoms, grids)
        if h is not None
    )
    _log(logger, f"  {len(valid)} pages with 款/項 headers")

    segments: tuple[tuple[PageHeader, tuple[Cell, ...]], ...] = tuple(
        segment
        for h, g, gr in valid
        for segment in split_page_sections(h, merge_rows(assign_words_to_cells(g, gr)))
    )
    _log(logger, f"  {len(segments)} segments (after mid-page splits)")

    sections = tuple(
        (key_header, tuple(cells for _, cells in group_segs))
        for key_header, group_segs in (
            (PageHeader(*key), tuple(grp))
            for key, grp in groupby(
                segments,
                key=lambda t: (t[0].kan_number, t[0].kan_name, t[0].kou_number, t[0].kou_name),
            )
        )
    )
    _log(logger, f"  {len(sections)} sections (款/項)")
    return sections


def flatten_section_cells(section: SectionCells) -> SectionRows:
    header, cell_groups = section
    budgets = tuple(parse_page_budget(cells) for cells in cell_groups)
    return (header, flatten_all_pages(budgets))


def flatten_sections(sections: Sequence[SectionCells]) -> tuple[SectionRows, ...]:
    return tuple(map(flatten_section_cells, sections))


def rows_from_sections(
    sections: Sequence[SectionRows],
    ffill_fields: tuple[str, ...] | None = None,
) -> tuple[FlatRow, ...]:
    transformed = tuple(
        (
            header,
            ffill(rows, ffill_fields) if ffill_fields else rows,
        )
        for header, rows in sections
    )
    return tuple(
        row
        for header, rows in transformed
        for row in label_section(header, rows)
    )


def rows_from_pdf(
    src_path: str,
    logger: Logger | None = None,
    ffill_fields: tuple[str, ...] | None = None,
) -> tuple[FlatRow, ...]:
    sections = collect_section_cells(src_path, logger=logger)
    section_rows = flatten_sections(sections)
    return rows_from_sections(section_rows, ffill_fields=ffill_fields)

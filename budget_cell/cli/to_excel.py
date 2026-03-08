"""
CLI: Multi-page PDF → Excel.

Pipeline:
  extract → filter(歳出) → grid
    → header(款/項) + cells → parse
    → flatten → stamp → ffill(kan/kou) → sectioned_ffill(moku/setsu) → Excel

Usage:
  python -m budget_cell.cli.to_excel <input.pdf> <output.xlsx>
"""

from __future__ import annotations

import sys

from budget_cell.extract import extract_all_geometries
from budget_cell.grid import build_grid, extract_expenditure_pages
from budget_cell.header import parse_page_header
from budget_cell.cells import assign_words_to_cells
from budget_cell.parse import parse_page_budget
from budget_cell.flatten import (
    HEADERS, KAN_KOU_FIELDS, MOKU_FIELDS, SETSU_FIELDS,
    flatten_page_budget, stamp_page, ffill, sectioned_ffill,
    row_to_tuple,
)


def _write_excel(rows: tuple, dst_path: str) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Budget"

    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="DAEEF3", end_color="DAEEF3", fill_type="solid")
    for ci, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for ri, row in enumerate(rows, 2):
        t = row_to_tuple(row)
        for ci, val in enumerate(t, 1):
            ws.cell(row=ri, column=ci, value=val)

    ws.auto_filter.ref = ws.dimensions
    wb.save(dst_path)


def process_pdf_to_excel(src_path: str, dst_path: str) -> None:
    print(f"Extracting geometries from {src_path}...")
    all_geoms = extract_all_geometries(src_path)
    print(f"  {len(all_geoms)} pages total")

    geoms = extract_expenditure_pages(all_geoms)
    print(f"  {len(geoms)} expenditure pages (after 歳出 title page)")

    print("Building grids...")
    grids = tuple(map(build_grid, geoms))

    print("Extracting page headers (款/項)...")
    headers = tuple(parse_page_header(g, gr) for g, gr in zip(geoms, grids))
    n_with_header = sum(1 for h in headers if h is not None)
    print(f"  {n_with_header} pages with 款/項 headers")

    print("Building cells + parsing budgets...")
    # Process only pages with headers (= budget data pages)
    pages = tuple(
        (h, g, gr)
        for h, g, gr in zip(headers, geoms, grids)
        if h is not None
    )

    per_page_rows = tuple(
        stamp_page(h, flatten_page_budget(
            parse_page_budget(assign_words_to_cells(g, gr))
        ))
        for h, g, gr in pages
    )

    print("Forward-filling...")
    # Step 1: ffill kan/kou across all rows (page header context)
    all_rows = tuple(row for page in per_page_rows for row in page)
    with_kan_kou = ffill(all_rows, KAN_KOU_FIELDS)

    # Step 2: sectioned ffill for moku/setsu, scoped by (kan, kou)
    filled = sectioned_ffill(
        with_kan_kou,
        (*MOKU_FIELDS, *SETSU_FIELDS),
        section_key=KAN_KOU_FIELDS,
    )
    print(f"  {len(filled)} rows")

    print(f"Writing Excel: {dst_path}")
    _write_excel(filled, dst_path)
    print("Done.")


def main() -> None:
    usage = "Usage: python -m budget_cell.cli.to_excel <input.pdf> <output.xlsx>"
    src = sys.argv[1] if len(sys.argv) > 1 else None
    dst = sys.argv[2] if len(sys.argv) > 2 else None

    _ = (
        process_pdf_to_excel(src, dst) if src and dst else
        (print(usage), sys.exit(1))
    )


if __name__ == "__main__":
    main()

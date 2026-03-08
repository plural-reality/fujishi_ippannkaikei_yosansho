"""
CLI: PDF -> Excel convenience wrapper.

Preferred composable pipeline:
  pdf_to_rows | rows_ffill | rows_to_excel

This command keeps backward compatibility by composing the same stages in-process.
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.excel_io import OutputLayout, write_rows_to_excel_path
from budget_cell.flatten import FFILL_FIELDS, sectioned_ffill
from budget_cell.pipeline import rows_from_pdf
from budget_cell.types import FlatRow


def _parse_csv_fields(raw: str) -> tuple[str, ...]:
    return tuple(
        field.strip()
        for field in raw.split(",")
        if field.strip()
    )


def _section_key(row: FlatRow) -> tuple[str, str]:
    return (row.kan_name, row.kou_name)


def process_pdf_to_excel(
    src_path: str,
    dst_path: str,
    layout: OutputLayout = "wide",
    ffill_fields: tuple[str, ...] | None = FFILL_FIELDS,
) -> None:
    rows = rows_from_pdf(src_path, logger=print, ffill_fields=None)
    final_rows = (
        sectioned_ffill(rows, ffill_fields, key_fn=_section_key)
        if ffill_fields
        else rows
    )
    print(f"Writing Excel ({layout}): {dst_path}")
    write_rows_to_excel_path(final_rows, dst_path, layout=layout)
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.to_excel",
        description="Convert budget PDF to Excel (wrapper over composable stages).",
    )
    parser.add_argument("src", help="input PDF path")
    parser.add_argument("dst", help="output xlsx path")
    parser.add_argument(
        "--layout",
        choices=("wide", "long"),
        default="wide",
        help="output layout (default: wide)",
    )
    parser.add_argument(
        "--ffill-fields",
        default=",".join(FFILL_FIELDS),
        help="comma-separated FlatRow fields to forward-fill",
    )
    parser.add_argument(
        "--no-ffill",
        action="store_true",
        help="disable forward-fill stage",
    )
    args = parser.parse_args(sys.argv[1:])
    fields = None if args.no_ffill else _parse_csv_fields(args.ffill_fields)
    process_pdf_to_excel(args.src, args.dst, layout=args.layout, ffill_fields=fields)


if __name__ == "__main__":
    main()

"""
CLI: PDF -> long Excel.

Canonical extraction entry point.
All downstream tools (long2short, long2trend) consume long Excel.

  nix run .#pdf2long -- <input.pdf> <output.xlsx>
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.excel_io import write_rows_to_excel_path
from budget_cell.flatten import FFILL_FIELDS, sectioned_ffill
from budget_cell.pipeline import rows_from_pdf
from budget_cell.types import FlatRow


_section_key = lambda row: (row.kan_name, row.kou_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdf2long",
        description="Extract budget PDF into long-format Excel (canonical hub format).",
    )
    parser.add_argument("src", help="input PDF path")
    parser.add_argument("dst", help="output long xlsx path")
    parser.add_argument(
        "--no-ffill",
        action="store_true",
        help="disable forward-fill stage",
    )
    args = parser.parse_args(sys.argv[1:])

    print(f"Extracting: {args.src}", file=sys.stderr)
    raw_rows = rows_from_pdf(args.src, logger=lambda msg: print(f"  {msg}", file=sys.stderr), ffill_fields=None)
    rows = (
        raw_rows
        if args.no_ffill
        else sectioned_ffill(raw_rows, FFILL_FIELDS, key_fn=_section_key)
    )
    write_rows_to_excel_path(rows, args.dst, layout="long")
    print(f"Wrote long Excel ({len(rows)} rows): {args.dst}", file=sys.stderr)


if __name__ == "__main__":
    main()

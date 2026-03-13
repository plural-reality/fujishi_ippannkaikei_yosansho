"""
CLI: long Excel x N -> comparison Excel.

Consumes multiple year-labeled long Excels and produces a comparison workbook.

  nix run .#long2comparison -- --input R6=r6.xlsx --input R8=r8.xlsx out.xlsx
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.excel_io import read_rows_from_excel_path
from budget_cell.matchers import MATCHERS
from budget_cell.comparison import load_year_excel_nodes, write_comparison_excel


_parse_year_input = lambda raw: (
    (parts := raw.split("=", 1)) and len(parts) == 2 and parts[0].strip() and parts[1].strip()
    and (parts[0].strip(), parts[1].strip())
) or ("", "")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="long2comparison",
        description="Create year-over-year comparison workbook from long-format Excels.",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="year-labeled input in YEAR=PATH form (repeatable)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=200,
        help="top N rows for short sheets (default: 200)",
    )
    parser.add_argument(
        "--matcher",
        choices=tuple(sorted(MATCHERS.keys())),
        default="loose",
        help="matching strategy for cross-year key alignment (default: loose)",
    )
    parser.add_argument("dst", help="output xlsx path")
    args = parser.parse_args(sys.argv[1:])

    year_to_path = {
        year: path
        for raw in args.input
        for year, path in (_parse_year_input(raw),)
        if year and path
    }
    _ = len(year_to_path) >= 2 or sys.exit("need at least 2 --input YEAR=PATH values")

    nodes = load_year_excel_nodes(year_to_path, read_rows_from_excel_path)
    write_comparison_excel(
        args.dst,
        nodes,
        top_n=args.top_n,
        match_id_fn=MATCHERS[args.matcher],
    )
    print(f"Wrote comparison workbook: {args.dst}", file=sys.stderr)


if __name__ == "__main__":
    main()

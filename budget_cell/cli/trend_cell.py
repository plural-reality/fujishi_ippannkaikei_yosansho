"""
CLI: build year-over-year trend Excel from year-labeled input Excels.

Decoupled by design:
  input contract is only Excel files (no PDF/pipeline dependency).
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.excel_io import read_rows_from_excel_path
from budget_cell.trend import load_year_excel_nodes, write_trend_excel


def _parse_year_input(raw: str) -> tuple[str, str]:
    parts = raw.split("=", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 and parts[0].strip() and parts[1].strip() else ("", "")


def _collect_year_inputs(values: tuple[str, ...]) -> dict[str, str]:
    pairs = tuple(_parse_year_input(value) for value in values)
    return {
        year: path
        for year, path in pairs
        if year and path
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.trend_cell",
        description="Create YoY trend Excel from year-tagged input Excels.",
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
    parser.add_argument("dst", help="output xlsx path")
    args = parser.parse_args(sys.argv[1:])
    year_to_path = _collect_year_inputs(tuple(args.input))
    if len(year_to_path) < 2:
        raise SystemExit("need at least 2 --input YEAR=PATH values")

    nodes = load_year_excel_nodes(year_to_path, read_rows_from_excel_path)
    write_trend_excel(args.dst, nodes, top_n=args.top_n)
    print(f"Wrote trend workbook: {args.dst}")


if __name__ == "__main__":
    main()

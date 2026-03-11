"""
CLI: long Excel -> short (wide) Excel.

Long is the canonical hub format; short/wide is a human-readable projection.

  nix run .#long2short -- <input-long.xlsx> <output-short.xlsx>
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.excel_io import read_rows_from_excel_path, write_rows_to_excel_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="long2short",
        description="Project long-format Excel into short (wide) Excel for human viewing.",
    )
    parser.add_argument("src", help="input long xlsx path")
    parser.add_argument("dst", help="output short xlsx path")
    args = parser.parse_args(sys.argv[1:])

    rows = read_rows_from_excel_path(args.src)
    write_rows_to_excel_path(rows, args.dst, layout="wide")
    print(f"Wrote short Excel ({len(rows)} rows): {args.dst}", file=sys.stderr)


if __name__ == "__main__":
    main()

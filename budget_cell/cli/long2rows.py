"""
CLI: long Excel -> NDJSON FlatRow stream.

Inverse of the Excel sink — feeds back into the Unix pipe ecosystem.

  nix run .#long2rows -- <input-long.xlsx> > rows.ndjson
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.excel_io import read_rows_from_excel_bytes, read_rows_from_excel_path
from budget_cell.row_stream import write_rows_ndjson


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="long2rows",
        description="Read long-format Excel and emit NDJSON FlatRow stream.",
    )
    parser.add_argument("src", help="input xlsx path or '-' for stdin bytes")
    args = parser.parse_args(sys.argv[1:])

    rows = (
        read_rows_from_excel_bytes(sys.stdin.buffer.read())
        if args.src == "-"
        else read_rows_from_excel_path(args.src)
    )
    write_rows_ndjson(sys.stdout, rows)
    print(f"Emitted {len(rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()

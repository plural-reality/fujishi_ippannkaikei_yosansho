"""
CLI: Excel source -> NDJSON FlatRow stream.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from budget_cell.excel_io import read_rows_from_excel_bytes, read_rows_from_excel_path
from budget_cell.row_stream import write_rows_ndjson


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.excel_to_rows",
        description="Read budget Excel and emit FlatRow NDJSON.",
    )
    parser.add_argument("src", help="input xlsx path or '-' for stdin bytes")
    args = parser.parse_args(sys.argv[1:])

    rows = (
        read_rows_from_excel_bytes(sys.stdin.buffer.read())
        if args.src == "-"
        else read_rows_from_excel_path(args.src)
    )
    write_rows_ndjson(sys.stdout, rows)
    print(f"Read {len(rows)} rows from {Path(args.src) if args.src != '-' else 'stdin'}", file=sys.stderr)


if __name__ == "__main__":
    main()

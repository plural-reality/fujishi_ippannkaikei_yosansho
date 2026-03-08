"""
CLI: NDJSON FlatRow stream -> Excel sink.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from budget_cell.excel_io import OutputLayout, write_rows_to_excel_bytes, write_rows_to_excel_path
from budget_cell.row_stream import read_rows_ndjson


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.rows_to_excel",
        description="Project FlatRow NDJSON to Excel (wide/long).",
    )
    parser.add_argument("dst", help="output xlsx path or '-' for stdout bytes")
    parser.add_argument(
        "--layout",
        choices=("wide", "long"),
        default="wide",
        help="output layout (default: wide)",
    )
    args = parser.parse_args(sys.argv[1:])
    layout: OutputLayout = args.layout

    rows = read_rows_ndjson(sys.stdin)
    _ = (
        sys.stdout.buffer.write(write_rows_to_excel_bytes(rows, layout=layout))
        if args.dst == "-"
        else write_rows_to_excel_path(rows, args.dst, layout=layout)
    )
    _ = (
        None
        if args.dst == "-"
        else print(f"Wrote {len(rows)} rows to {Path(args.dst)}", file=sys.stderr)
    )


if __name__ == "__main__":
    main()

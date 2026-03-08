"""
CLI: PDF -> NDJSON FlatRow stream.

Composable source stage. No Excel concerns, no forward-fill by default.
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.pipeline import rows_from_pdf
from budget_cell.row_stream import write_rows_ndjson


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.pdf_to_rows",
        description="Extract FlatRow NDJSON from budget PDF.",
    )
    parser.add_argument("src", help="input PDF path")
    args = parser.parse_args(sys.argv[1:])

    rows = rows_from_pdf(args.src, logger=_log, ffill_fields=None)
    write_rows_ndjson(sys.stdout, rows)


if __name__ == "__main__":
    main()

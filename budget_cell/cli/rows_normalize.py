"""
CLI: NDJSON FlatRow stream -> NDJSON FlatRow stream (text normalization).

Applies NFKC normalization and removes all whitespace from text fields.
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.flatten import NORMALIZE_TEXT_FIELDS, normalize_text
from budget_cell.row_stream import read_rows_ndjson, write_rows_ndjson


def _parse_csv_fields(raw: str) -> tuple[str, ...]:
    return tuple(
        field.strip()
        for field in raw.split(",")
        if field.strip()
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.rows_normalize",
        description="Normalize FlatRow text fields (NFKC + strip spaces).",
    )
    parser.add_argument(
        "--fields",
        default=",".join(NORMALIZE_TEXT_FIELDS),
        help="comma-separated FlatRow fields to normalize",
    )
    args = parser.parse_args(sys.argv[1:])

    fields = _parse_csv_fields(args.fields)
    rows = read_rows_ndjson(sys.stdin)
    normalized = normalize_text(rows, fields)
    write_rows_ndjson(sys.stdout, normalized)


if __name__ == "__main__":
    main()

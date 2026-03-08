"""
CLI: NDJSON FlatRow stream -> NDJSON FlatRow stream (forward-fill).
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.flatten import FFILL_FIELDS, ffill, sectioned_ffill
from budget_cell.row_stream import read_rows_ndjson, write_rows_ndjson
from budget_cell.types import FlatRow


def _parse_csv_fields(raw: str) -> tuple[str, ...]:
    return tuple(
        field.strip()
        for field in raw.split(",")
        if field.strip()
    )


def _key_fn(fields: tuple[str, ...]):
    return lambda row: tuple(getattr(row, field) for field in fields)


def _apply_ffill(
    rows: tuple[FlatRow, ...],
    fields: tuple[str, ...],
    section_fields: tuple[str, ...],
) -> tuple[FlatRow, ...]:
    return (
        sectioned_ffill(rows, fields, key_fn=_key_fn(section_fields))
        if section_fields
        else ffill(rows, fields)
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.rows_ffill",
        description="Forward-fill FlatRow NDJSON.",
    )
    parser.add_argument(
        "--fields",
        default=",".join((*FFILL_FIELDS, "setsumei_code")),
        help="comma-separated FlatRow fields to forward-fill",
    )
    parser.add_argument(
        "--section-fields",
        default="kan_name,kou_name",
        help="comma-separated key fields for sectioned fill (empty to disable)",
    )
    args = parser.parse_args(sys.argv[1:])

    fields = _parse_csv_fields(args.fields)
    section_fields = _parse_csv_fields(args.section_fields)
    rows = read_rows_ndjson(sys.stdin)
    filled = _apply_ffill(rows, fields, section_fields)
    write_rows_ndjson(sys.stdout, filled)


if __name__ == "__main__":
    main()

"""
CLI: verify Excel-derived FlatRows against a field/pattern contract.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import fields
from typing import Sequence

from budget_cell.excel_io import read_rows_from_excel_path
from budget_cell.types import FlatRow


_DEFAULT_PATTERN = r"^[0-9０-９]+項$"
_FIELD_NAMES = tuple(field.name for field in fields(FlatRow))


def _compile_pattern(raw: str) -> re.Pattern[str]:
    return re.compile(raw)


def _field_value(row: FlatRow, field_name: str) -> str:
    value = getattr(row, field_name)
    return value if isinstance(value, str) else "" if value is None else str(value)


def find_matches(
    rows: Sequence[FlatRow],
    field_name: str,
    pattern: re.Pattern[str],
) -> tuple[tuple[int, FlatRow], ...]:
    return tuple(
        (index, row)
        for index, row in enumerate(rows, start=2)
        if bool(pattern.search(_field_value(row, field_name)))
    )


def _format_match(field_name: str, item: tuple[int, FlatRow]) -> str:
    index, row = item
    return (
        f"{index}: {field_name}={_field_value(row, field_name)!r} "
        f"款={row.kan_name!r} 項={row.kou_name!r} "
        f"節={row.setsu_name!r} 事業コード={row.setsumei_code!r} 説明={row.setsumei_name!r}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.verify_excel",
        description="Verify that a FlatRow field in Excel does not match a forbidden pattern.",
    )
    parser.add_argument("src", help="input xlsx path")
    parser.add_argument(
        "--field",
        choices=_FIELD_NAMES,
        default="moku_name",
        help="FlatRow field to inspect (default: moku_name)",
    )
    parser.add_argument(
        "--pattern",
        default=_DEFAULT_PATTERN,
        help=f"regex to detect forbidden values (default: {_DEFAULT_PATTERN})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="number of sample matches to print (default: 10)",
    )
    parser.add_argument(
        "--allow-hits",
        action="store_true",
        help="exit 0 even when matches are found",
    )
    args = parser.parse_args(sys.argv[1:])

    rows = read_rows_from_excel_path(args.src)
    matches = find_matches(rows, args.field, _compile_pattern(args.pattern))

    print(f"rows {len(rows)}")
    print(f"hits {len(matches)}")
    _ = tuple(print(_format_match(args.field, item)) for item in matches[: args.limit])
    _ = sys.exit(0 if args.allow_hits or not matches else 1)


if __name__ == "__main__":
    main()

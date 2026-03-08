"""
FlatRow NDJSON adapters.

This module keeps stream wiring (stdin/stdout) separate from transformation logic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from typing import Iterable, Mapping, TextIO

from budget_cell.types import FlatRow


FLAT_ROW_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(FlatRow))


def flat_row_to_mapping(row: FlatRow) -> dict[str, object]:
    return asdict(row)


def mapping_to_flat_row(raw: Mapping[str, object]) -> FlatRow:
    payload = {name: raw.get(name) for name in FLAT_ROW_FIELDS}
    return FlatRow(**payload)


def parse_rows_ndjson(lines: Iterable[str]) -> tuple[FlatRow, ...]:
    return tuple(
        mapping_to_flat_row(json.loads(line))
        for line in lines
        if line.strip()
    )


def read_rows_ndjson(stream: TextIO) -> tuple[FlatRow, ...]:
    return parse_rows_ndjson(stream)


def encode_rows_ndjson(rows: Iterable[FlatRow]) -> tuple[str, ...]:
    return tuple(
        json.dumps(flat_row_to_mapping(row), ensure_ascii=False)
        for row in rows
    )


def write_rows_ndjson(stream: TextIO, rows: Iterable[FlatRow]) -> None:
    _ = stream.write("".join(f"{line}\n" for line in encode_rows_ndjson(rows)))

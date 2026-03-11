from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from budget_cell.cli.verify_excel import find_matches
from budget_cell.excel_io import write_rows_to_excel_path
from budget_cell.types import FlatRow


def _row(**overrides: object) -> FlatRow:
    defaults = dict(
        kan_name="総務費",
        kou_name="総務管理費",
        moku_name="1 一般管理費",
        honendo=2074044,
        zenendo=2122248,
        hikaku=-48204,
        kokuken=318167,
        chihousei=None,
        sonota=23854,
        ippan=7519634,
        setsu_number=2,
        setsu_name="給料",
        setsu_amount=765532,
        sub_item_name="",
        sub_item_amount=None,
        setsumei_code="001",
        setsumei_level=1,
        setsumei_name="給与費",
        setsumei_amount=442593,
    )
    return FlatRow(**{**defaults, **overrides})


def test_find_matches_detects_forbidden_moku_pattern() -> None:
    rows = (
        _row(),
        _row(moku_name="１項"),
    )

    matches = find_matches(rows, "moku_name", re.compile(r"^[0-9０-９]+項$"))

    assert tuple(index for index, _ in matches) == (3,)
    assert matches[0][1].moku_name == "１項"


def test_verify_excel_cli_fails_when_hits_exist(tmp_path: Path) -> None:
    dst = tmp_path / "with-hit.xlsx"
    write_rows_to_excel_path((_row(moku_name="１項"),), str(dst), layout="wide")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budget_cell.cli.verify_excel",
            str(dst),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "hits 1" in result.stdout


def test_verify_excel_cli_passes_when_no_hits_exist(tmp_path: Path) -> None:
    dst = tmp_path / "clean.xlsx"
    write_rows_to_excel_path((_row(),), str(dst), layout="wide")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budget_cell.cli.verify_excel",
            str(dst),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "hits 0" in result.stdout


def test_verify_excel_cli_allow_hits_returns_zero(tmp_path: Path) -> None:
    dst = tmp_path / "allowed-hit.xlsx"
    write_rows_to_excel_path((_row(moku_name="１項"),), str(dst), layout="wide")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budget_cell.cli.verify_excel",
            str(dst),
            "--allow-hits",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "hits 1" in result.stdout


def test_verify_excel_cli_supports_custom_field_and_pattern(tmp_path: Path) -> None:
    dst = tmp_path / "custom-field.xlsx"
    write_rows_to_excel_path((_row(setsu_name="工事請負費"),), str(dst), layout="wide")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budget_cell.cli.verify_excel",
            str(dst),
            "--field",
            "setsu_name",
            "--pattern",
            "工事",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "setsu_name='工事請負費'" in result.stdout

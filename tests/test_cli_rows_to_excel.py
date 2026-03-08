from __future__ import annotations

import subprocess
import sys


def test_rows_to_excel_rejects_empty_stdin(tmp_path) -> None:
    dst = tmp_path / "empty.xlsx"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "budget_cell.cli.rows_to_excel",
            str(dst),
            "--layout",
            "long",
        ],
        input="",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "no FlatRow records received on stdin" in result.stderr
    assert not dst.exists()

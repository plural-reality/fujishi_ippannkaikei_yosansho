{
  description = "budget-cell — PDF budget table extraction pipeline";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;
        pythonPkgs = python.pkgs;

        deps = [
          pythonPkgs.pdfplumber
          pythonPkgs.pymupdf
          pythonPkgs.openpyxl
        ];

        devDeps = [
          pythonPkgs.pytest
        ];

        src = ./.;
        pythonEnv = python.withPackages (_: deps ++ devDeps);
        mkPythonApp = appName: module: {
          type = "app";
          program = toString (pkgs.writeShellScript "run-${appName}" ''
            exec ${pythonEnv}/bin/python -m ${module} "$@"
          '');
          meta.description = "Run ${module}";
        };
        mkCheck = checkName: script:
          pkgs.runCommand checkName { } ''
            export PYTHONDONTWRITEBYTECODE=1
            export TMPDIR="$(mktemp -d)"
            cd ${src}
            ${script}
            touch "$out"
          '';
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];
          shellHook = ''
            export PYTHONDONTWRITEBYTECODE=1
          '';
        };

        # nix run .#test
        apps.test = {
          type = "app";
          program = toString (pkgs.writeShellScript "run-tests" ''
            exec ${pythonEnv}/bin/python -m pytest tests/ -q "$@"
          '');
          meta.description = "Run pytest";
        };

        # nix run .#overlay -- <input.pdf> <output.pdf>
        apps.overlay = mkPythonApp "overlay" "budget_cell.cli.overlay";
        apps."excel-to-rows" = mkPythonApp "excel-to-rows" "budget_cell.cli.excel_to_rows";
        apps."make-spread" = mkPythonApp "make-spread" "budget_cell.cli.make_spread";
        apps."pdf-to-rows" = mkPythonApp "pdf-to-rows" "budget_cell.cli.pdf_to_rows";
        apps."rows-ffill" = mkPythonApp "rows-ffill" "budget_cell.cli.rows_ffill";
        apps."rows-to-excel" = mkPythonApp "rows-to-excel" "budget_cell.cli.rows_to_excel";
        apps."to-excel" = mkPythonApp "to-excel" "budget_cell.cli.to_excel";
        apps."trend-cell" = mkPythonApp "trend-cell" "budget_cell.cli.trend_cell";
        apps."verify-excel" = mkPythonApp "verify-excel" "budget_cell.cli.verify_excel";
        apps."visualize-geometry" = mkPythonApp "visualize-geometry" "budget_cell.cli.visualize_geometry";

        checks.pytest = mkCheck "budget-cell-pytest" ''
          ${pythonEnv}/bin/python -m pytest tests/ -q
        '';

        checks.r6-regression = mkCheck "budget-cell-r6-regression" ''
          ${pythonEnv}/bin/python - <<'PY'
          import re
          from dataclasses import replace
          from budget_cell.excel_io import read_rows_from_excel_path
          from budget_cell.flatten import FFILL_FIELDS, sectioned_ffill
          from budget_cell.pipeline import rows_from_pdf

          pattern = re.compile(r"^[0-9０-９]+項$")

          pdf_rows = sectioned_ffill(
              rows_from_pdf("tests/fixtures/r6/budget_spread_cover1_v3.pdf", ffill_fields=None),
              FFILL_FIELDS,
              key_fn=lambda row: (row.kan_name, row.kou_name),
          )
          short_rows = read_rows_from_excel_path("tests/fixtures/r6/budget_spread_cover1_short_v3.xlsx")
          long_rows = read_rows_from_excel_path("tests/fixtures/r6/budget_spread_cover1_long_v3.xlsx")

          hits = tuple(
              (label, index, row.moku_name, row.kan_name, row.kou_name)
              for label, rows in (
                  ("pdf", pdf_rows),
                  ("short", short_rows),
                  ("long", long_rows),
              )
              for index, row in enumerate(rows, start=2)
              if bool(pattern.search(row.moku_name))
          )
          normalize_wide = lambda row: replace(
              row,
              setsumei_level=row.setsumei_level if row.setsumei_name else None,
          )

          print(f"pdf_rows {len(pdf_rows)}")
          print(f"short_rows {len(short_rows)}")
          print(f"long_rows {len(long_rows)}")
          print(f"hits {len(hits)}")
          print(hits[:10])
          print(f"long_matches_pdf {long_rows == pdf_rows}")
          print(f"short_matches_pdf {tuple(map(normalize_wide, pdf_rows)) == short_rows}")
          raise SystemExit(
              0
              if (
                  not hits
                  and long_rows == pdf_rows
                  and tuple(map(normalize_wide, pdf_rows)) == short_rows
              )
              else 1
          )
          PY
        '';

        checks.r6-pdf-to-short-regression = mkCheck "budget-cell-r6-pdf-to-short-regression" ''
          ${pythonEnv}/bin/python - <<'PY'
          import os
          import re
          from pathlib import Path

          from budget_cell.cli.to_excel import process_pdf_to_excel
          from budget_cell.excel_io import read_rows_from_excel_path

          src_pdf = "tests/fixtures/r6/budget_spread_cover1_v3.pdf"
          src_xlsx = "tests/fixtures/r6/budget_spread_cover1_short_v3.xlsx"
          dst_xlsx = Path(os.environ["TMPDIR"]) / "result-r6-short.xlsx"
          pattern = re.compile(r"^[0-9０-９]+項$")

          process_pdf_to_excel(src_pdf, str(dst_xlsx), layout="wide")

          expected = read_rows_from_excel_path(src_xlsx)
          actual = read_rows_from_excel_path(str(dst_xlsx))
          hits = tuple(
              (index, row.moku_name, row.kan_name, row.kou_name)
              for index, row in enumerate(actual, start=2)
              if bool(pattern.search(row.moku_name))
          )

          print(f"expected_rows {len(expected)}")
          print(f"actual_rows {len(actual)}")
          print(f"hits {len(hits)}")
          raise SystemExit(1 if hits or actual != expected else 0)
          PY
        '';
      }
    );
}

# 富士市一般会計予算書 `budget_cell`

`budget_cell` は PDF の表セルを `FlatRow` ストリームへ変換し、必要に応じて Excel へ投影するパイプラインです。正準構成は `flake.nix` に寄せてあり、実装は `budget_cell/`、検証は `tests/`、回帰 fixture は `tests/fixtures/` に集約しています。

## Canonical Layout

```text
.
├── flake.nix
├── flake.lock
├── README.md
├── budget_cell/
│   ├── ARCHITECTURE.md
│   ├── cli/
│   └── *.py
└── tests/
    ├── fixtures/
    │   └── r6/
    │       ├── budget_spread_cover1_v3.pdf
    │       ├── budget_spread_cover1_short_v3.xlsx
    │       └── budget_spread_cover1_long_v3.xlsx
    └── test_*.py
```

## Pipeline

```text
PDF
  -> `nix run .#pdf-to-rows`
NDJSON (`FlatRow`)
  -> `nix run .#rows-ffill -- --fields ...`
NDJSON (`FlatRow`)
  -> `nix run .#rows-to-excel -- --layout wide|long <output.xlsx>`
Excel
```

`nix run .#to-excel` は上の source / transform / sink を同一プロセスで合成する互換ラッパです。

## Commands

```bash
nix develop
nix run .#test
nix run .#pdf-to-rows -- path/to/input.pdf
nix run .#rows-ffill -- --fields kan_name kou_name
nix run .#rows-to-excel -- --layout long path/to/output.xlsx
nix run .#to-excel -- path/to/input.pdf path/to/output.xlsx --layout wide
nix run .#overlay -- path/to/input.pdf path/to/output.pdf
nix run .#make-spread -- path/to/input.pdf path/to/output.pdf
nix run .#trend-cell -- --input R6=path/to/r6.xlsx --input R8=path/to/r8.xlsx path/to/output.xlsx
nix run .#verify-excel -- path/to/workbook.xlsx
```

## Verification

- `nix flake check`
  - `checks.pytest`
  - `checks.r6-regression`
  - `checks.r6-pdf-to-short-regression`
- `tests/fixtures/r6/`
  - R6 見開き PDF と short/long workbook の回帰基準

詳細な依存グラフとモジュール境界は `budget_cell/ARCHITECTURE.md` を参照してください。

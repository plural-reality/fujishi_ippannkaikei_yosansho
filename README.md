# 富士市一般会計予算書 `budget_cell`

`budget_cell` は PDF の表セルを `FlatRow` ストリームへ変換し、必要に応じて Excel へ投影するパイプラインです。正準構成は `flake.nix` に寄せてあり、実装、入力、回帰 fixture、生成物を別レイヤに分けています。

## Canonical Layout

```text
.
├── flake.nix
├── flake.lock
├── README.md
├── docs/
│   └── ARCHITECTURE.md
├── inputs/
│   ├── r6-budget.pdf
│   ├── r7-budget.pdf
│   └── r8-budget.pdf
├── budget_cell/
│   ├── cli/
│   └── *.py
├── tests/
│   ├── fixtures/
│   │   ├── r6/
│   │   │   ├── input/
│   │   │   │   └── budget-spread.pdf
│   │   │   └── expected/
│   │   │       ├── budget-spread-short.xlsx
│   │   │       └── budget-spread-long.xlsx
│   │   └── r8/
│   │       └── expected/
│   │           └── budget-long-ffill.xlsx
│   └── test_*.py
└── result/
    ├── .gitkeep
    └── r6-r8-trend-compare-loose.xlsx
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
nix run .#make-spread -- inputs/r6-budget.pdf result/r6-spread.pdf --head-single-pages 1
nix run .#pdf-to-rows -- inputs/r8-budget.pdf | nix run .#rows-ffill -- | nix run .#rows-to-excel -- result/r8-long-pipe.xlsx --layout long
nix run .#to-excel -- inputs/r8-budget.pdf result/r8-long.xlsx --layout long
nix run .#to-excel -- inputs/r8-budget.pdf result/r8-wide.xlsx --layout wide
nix run .#overlay -- inputs/r8-budget.pdf result/r8-overlay.pdf
nix run .#trend-cell -- --matcher loose --input R6=tests/fixtures/r6/expected/budget-spread-long.xlsx --input R8=tests/fixtures/r8/expected/budget-long-ffill.xlsx result/r6-r8-trend-compare-loose.xlsx
nix run .#verify-excel -- tests/fixtures/r6/expected/budget-spread-short.xlsx
```

## Verification

- `nix flake check`
  - `checks.pytest`
  - `checks.r6-regression`
  - `checks.r6-pdf-to-short-regression`
- `inputs/*.pdf`
  - 通常入力として扱う元 PDF
- `result/r6-spread.pdf`
  - R6 用の正準 spread 出力。生成コマンドは `--head-single-pages 1`
- `tests/fixtures/r6/`
  - `input/` は回帰テスト用入力
  - `expected/` は golden workbook
- `tests/fixtures/r8/expected/budget-long-ffill.xlsx`
  - 比較表生成の基準に使う R8 workbook
- `result/`
  - 実行生成物の退避先。Git 管理外
  - `r6-r8-trend-compare-loose.xlsx` は最終成果物の配置先

詳細な依存グラフとモジュール境界は `docs/ARCHITECTURE.md` を参照してください。

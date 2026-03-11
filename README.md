# 富士市一般会計予算書 `budget_cell`

`budget_cell` は PDF の表セルを `FlatRow` ストリームへ変換し、long Excel を正準フォーマットとして各種射影を行うパイプラインです。正準構成は `flake.nix` に寄せてあり、実装、入力、回帰 fixture、生成物を別レイヤに分けています。

## Pipeline

long Excel を hub とし、全ての変換はここを経由します。

```text
PDF ──→ pdf2long ──→ long Excel (canonical)
                         │
                         ├──→ long2short  ──→ short Excel (人間閲覧用)
                         ├──→ long2trend  ──→ trend Excel (年度比較)
                         └──→ long2rows   ──→ NDJSON (パイプ用)
```

## Commands

```bash
# PDF → long Excel (正準フォーマット)
nix run .#pdf2long -- inputs/r8-budget.pdf result/r8-long.xlsx

# long → short (ワイド表示)
nix run .#long2short -- result/r8-long.xlsx result/r8-short.xlsx

# 年度比較
nix run .#long2trend -- \
  --input R6=tests/fixtures/r6/expected/budget-spread-long.xlsx \
  --input R8=tests/fixtures/r8/expected/budget-long-ffill.xlsx \
  result/r6-r8-trend.xlsx

# long → NDJSON パイプ
nix run .#long2rows -- result/r8-long.xlsx | jq '.kan_name'

# ジオメトリ可視化
nix run .#visualize-geom -- inputs/r8-budget.pdf result/r8-geom.pdf

# 見開き PDF
nix run .#make-spread -- inputs/r6-budget.pdf result/r6-spread.pdf --head-single-pages 1

# テスト
nix run .#test
```

### Low-level pipe primitives

内部構成要素。上級者向け、または Unix パイプで合成する場合に使用。

```bash
nix run .#pdf-to-rows -- inputs/r8-budget.pdf \
  | nix run .#rows-ffill -- \
  | nix run .#rows-to-excel -- result/r8-long-pipe.xlsx --layout long
nix run .#excel-to-rows -- result/r8-long.xlsx > rows.ndjson
nix run .#overlay -- inputs/r8-budget.pdf result/r8-overlay.pdf
nix run .#verify-excel -- tests/fixtures/r6/expected/budget-spread-short.xlsx
```

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
    └── .gitkeep
```

## Verification

- `nix flake check`
  - `checks.pytest`
  - `checks.r6-regression`
  - `checks.r6-pdf-to-short-regression`
- `inputs/*.pdf` — 通常入力として扱う元 PDF
- `tests/fixtures/r6/` — `input/` は回帰テスト用入力、`expected/` は golden workbook
- `tests/fixtures/r8/expected/budget-long-ffill.xlsx` — 比較表生成の基準に使う R8 workbook
- `result/` — 実行生成物の退避先。Git 管理外

詳細な依存グラフとモジュール境界は `docs/ARCHITECTURE.md` を参照してください。

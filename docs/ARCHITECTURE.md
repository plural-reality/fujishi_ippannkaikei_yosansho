# Architecture — budget_cell

富士市一般会計予算書 PDF → NDJSON(FlatRow) → 構造化 Excel 変換パイプライン。

## 設計原則

- **不変データ**: 全ドメイン型は `frozen dataclass`。mutation なし。
- **純粋関数パイプライン**: 各モジュールは `f(input) → output` の純粋変換。IO は境界のみ。
- **疎結合**: 各変換ステップは独立。依存は `types.py` のみ共有。
- **関心の分離**: PDF読取 / 幾何正規化 / 幾何構造 / 表解析 / 正規化 / 出力 は完全に分離。

---

## 依存グラフ

```
types.py ← SSOT（全ドメイン型、依存なし）
  ↑
  ├── pipeline.py   ← 純粋合成: PDF path → SectionCells[] → SectionRows[]
  ├── extract.py    ← IO境界: pdfplumber
  ├── geometry_normalize.py ← 純粋: PageGeometry → PageGeometry（footer artifact 除去）
  ├── grid.py       ← 純粋: 幾何構造 → Grid
  ├── cells.py      ← 純粋: 幾何構造 × Grid → Cell[]
  ├── header.py     ← 純粋: 幾何構造 × Grid → PageHeader
  ├── merge.py      ← 純粋: Cell[] → Cell[]（複数行統合）
  ├── section.py    ← 純粋: Cell[] → (Header, Cell[])[]（項境界分割）
  ├── parse.py      ← 純粋: Cell[] → PageBudget
  ├── flatten.py    ← 純粋: PageBudget → FlatRow[]
  ├── row_stream.py ← FlatRow ↔ NDJSON adapter
  ├── excel_io.py   ← FlatRow ↔ Excel projection（wide/long）
  └── overlay.py    ← IO境界: fitz (pymupdf)

cli/
  ├── excel_to_rows.py ← Excel source → NDJSON(FlatRow) stdout
  ├── pdf_to_rows.py   ← パイプライン合成: PDF path → NDJSON(FlatRow) stdout
  ├── rows_ffill.py    ← 中間変換: NDJSON stdin → NDJSON stdout（fields指定可能）
  ├── rows_to_excel.py ← 出力境界: NDJSON stdin → Excel sink（wide/long projection）
  ├── to_excel.py      ← 互換ラッパ: pdf_to_rows | rows_ffill | rows_to_excel を同一プロセスで合成
  └── overlay.py    ← パイプライン合成: PDF → overlay PDF
```

---

## データ型（types.py — Single Source of Truth）

全型は `@dataclass(frozen=True)`。ロジックなし、IOなし、依存なし。

### PDF幾何層

```
Line(x0, y0, x1, y1, linewidth)
  @property is_vertical: bool
  @property is_horizontal: bool

Word(x0, y0, x1, y1, text)

PageGeometry(width, height, lines: tuple[Line,...], words: tuple[Word,...])

Grid(col_boundaries: tuple[float,...], row_boundaries: tuple[float,...])
```

### セル層

```
Cell(row: int, col: int, x0, y0, x1, y1, text: str, words: tuple[Word,...])
```

### ページヘッダ（表の上の款/項情報）

```
PageHeader(kan_number: str, kan_name: str, kou_number: str, kou_name: str)
```

### 予算構造層（表の中身）

```
SetsumeiEntry(kind: "coded"|"text", code: str|None, name: str,
              amount: int|None, level: int)

Zaigen(kokuken: int|None, chihousei: int|None, sonota: int|None, ippan: int|None)

SetsuRecord(number: int|None, name: str, amount: int|None,
            sub_items: tuple[(str, int|None),...],
            setsumei: tuple[SetsumeiEntry,...])

MokuRecord(name: str, honendo, zenendo, hikaku: int|None,
           zaigen: Zaigen, setsu_list: tuple[SetsuRecord,...])

PageBudget(moku_records: tuple[MokuRecord,...],
           orphan_setsu: tuple[SetsuRecord,...])
```

### 正規化出力層

```
FlatRow(
  kan_name, kou_name,                                    ← 款/項（label_section で付与）
  moku_name, honendo, zenendo, hikaku,                   ← 目
  kokuken, chihousei, sonota, ippan,                     ← 財源内訳
  setsu_number, setsu_name, setsu_amount,                ← 節
  sub_item_name, sub_item_amount,                        ← 小区分
  setsumei_code, setsumei_level, setsumei_name, setsumei_amount  ← 説明
)
```

---

## パイプライン詳細（Unix Pipe / 3段ストリーム）

### Source Normalization

抽出本線の前に、入力 PDF を読み取りやすい形へ正規化する任意ステージを置ける。
`make_spread` はこの層に属し、ドメイン抽出ではなく **source PDF -> normalized PDF** の変換だけを担当する。

```
raw PDF
 │
 ├─ optional: budget_cell.cli.make_spread
 │              └─ 単ページ列 → 見開き PDF
 │
 ▼ normalized PDF
```

R6 はこの前処理が必要なケースで、正準 recipe は
`nix run .#make-spread -- inputs/r6-budget.pdf result/r6-spread.pdf --head-single-pages 1`
である。1ページ目だけ単独保持し、2ページ目以降を 2-up 化する。
この結果を回帰 fixture として固定したものが `tests/fixtures/r6/input/budget-spread.pdf`。

```
normalized PDF path
 │
 ▼ budget_cell.cli.pdf_to_rows
 │   ├─ extract.py: extract_all_geometries
 │   ├─ geometry_normalize.py: normalize_page_geometries
 │   ├─ grid.py: extract_expenditure_pages → build_grid
 │   ├─ header.py: parse_page_header
 │   ├─ cells.py: assign_words_to_cells → merge.py: merge_rows → section.py: split_page_sections
 │   ├─ parse.py: parse_page_budget
 │   ├─ flatten.py: flatten_all_pages
 │   └─ flatten.py: label_section
 │
stdout: NDJSON(FlatRow)                            抽出結果（フォーマット非依存）
 │
 ▼ budget_cell.cli.rows_ffill --fields ...
stdin: NDJSON(FlatRow)
 │   └─ flatten.py: sectioned_ffill / ffill
stdout: NDJSON(FlatRow)                            中間変換（前方充填のみ）
 │
 ▼ budget_cell.cli.rows_to_excel --layout wide|long
stdin: NDJSON(FlatRow)
 │   ├─ projection: wide | long
 │   └─ openpyxl sink
Excel (.xlsx)                                      出力形式変換
```

- `rows_ffill` は **中間変換専用**（NDJSON→NDJSON）で、出力形式変換を持たない。
- `wide/long` は `rows_to_excel` の **投影** であり、PDF抽出・構造化ロジックとは非結合。
- 既存Excelを起点にする場合は `excel_to_rows | rows_ffill | rows_to_excel` で同一パイプを再利用できる。
- `make_spread` は `pdf_to_rows` の内部ではなく、その前段の **source normalization** に置く。
- footer page number 除去は PDF rewrite ではなく、`extract.py` 後の **geometry normalization** に置く。
- したがって pipeline 上の責務は `raw PDF -> normalized PDF -> normalized geometry -> NDJSON -> Excel` で分離される。

### 各ステップの変換

| ステップ | 入力型 | 出力型 | モジュール | 性質 |
|---|---|---|---|---|
| Source正規化（任意） | `raw PDF path` | `normalized PDF path` | cli/make_spread (`spread`) | IO |
| PDF読取 | `str (path)` | `tuple[PageGeometry,...]` | extract | IO |
| Geometry正規化 | `tuple[PageGeometry,...]` | `tuple[PageGeometry,...]` | geometry_normalize | 純粋 |
| 歳出フィルタ | `tuple[PageGeometry,...]` | `tuple[PageGeometry,...]` | grid | 純粋 |
| Grid構築 | `PageGeometry` | `Grid` | grid | 純粋 |
| ヘッダ抽出 | `PageGeometry × Grid` | `PageHeader \| None` | header | 純粋 |
| セル割当 | `PageGeometry × Grid` | `tuple[Cell,...]` | cells | 純粋 |
| 行統合 | `tuple[Cell,...]` | `tuple[Cell,...]` | merge | 純粋 |
| 項境界分割 | `PageHeader × tuple[Cell,...]` | `tuple[(PageHeader,tuple[Cell,...]),...]` | section | 純粋 |
| 予算解析 | `tuple[Cell,...]` | `PageBudget` | parse | 純粋 |
| フラット化 | `tuple[PageBudget,...]` | `tuple[FlatRow,...]` | flatten | 純粋 |
| 款項ラベル | `PageHeader × tuple[FlatRow,...]` | `tuple[FlatRow,...]` | flatten | 純粋 |
| Excel読取（任意） | `.xlsx file` | `NDJSON stream` | cli/excel_to_rows (`excel_io`) | IO |
| NDJSON出力 | `tuple[FlatRow,...]` | `NDJSON stream` | cli/pdf_to_rows | IO |
| 前方充填（任意） | `NDJSON(stdin) × fields` | `NDJSON(stdout)` | cli/rows_ffill (`flatten.sectioned_ffill`) | IO境界 + 純粋 |
| Excel投影/出力 | `NDJSON(stdin) × layout(wide\|long)` | `.xlsx file` | cli/rows_to_excel | IO |

---

## モジュール詳細

### extract.py — IO境界（pdfplumber）

パッケージ唯一の pdfplumber 依存。PDF バイト列をドメイン型に変換する境界。

- `extract_page_geometry(page) → PageGeometry` — 1ページの幾何情報抽出
- `extract_geometry_from_path(path, page_index=0) → PageGeometry` — 単一ページ
- `extract_all_geometries(path) → tuple[PageGeometry,...]` — 全ページ map

### geometry_normalize.py — PageGeometry 正規化

`extract.py` の lossless な出力を保ったまま、表外の footer artifact を除去する純粋変換。
R6 spread fixture ではページ番号 `- 240 -` 系が `Word` として現れ、horizontal line が欠落した
ページでは `grid.py` の row clustering に混ざるため、この段階で `PageGeometry.words` から落とす。

- `normalize_page_geometry(geom) → PageGeometry`
- `normalize_page_geometries(geoms) → tuple[PageGeometry,...]`

### grid.py — 幾何構造 → Grid

縦罫線の X 座標 → 列境界、Word の Y 座標クラスタリング → 行境界。
歳出セクション検出は「歳 出」扉ページ（テキスト一致 + 罫線なし）で判定。

- `build_grid(geom) → Grid`
- `is_expenditure_page(geom) → bool` — 縦罫線の有無
- `extract_expenditure_pages(geoms) → tuple[PageGeometry,...]` — 扉ページ以降の表ページ

### cells.py — Word → Cell 割当

各 Word を Grid の (row, col) にマッピング。同一セルの Word は結合。

- `assign_words_to_cells(geom, grid) → tuple[Cell,...]`

### header.py — 表上ヘッダ抽出

表の上方（Grid外）の Word 群から `N款 名前` `N項 名前` パターンを検出。
非データページ（給与費明細書等）は `None` を返す。

- `parse_page_header(geom, grid) → PageHeader | None`

### merge.py — 複数行テキスト統合

左表（col 0-7, アンカー=col 1 本年度予算額）と右表（col 9-11, アンカー=col 10 金額）を
**独立して**統合。アンカー列に値がある行が論理行の開始、空行は前行への継続。

これにより、目名が幅の都合で折り返される一方で節が新しいエントリを開始するケースを正しく処理。

- `merge_rows(cells) → tuple[Cell,...]`

### section.py — ページ内の款/項境界分割

1ページ内に複数の(款,項)セクションが含まれるケースを検出・分割。
ページ上端ヘッダではなく、表セル内に現れる款/項 marker を SSOT として扱い、
小計行・繰り返し表ヘッダ・中間の款/項ラベル行を除去しながら境界を確定する。

- `split_page_sections(header, cells) → tuple[(PageHeader, tuple[Cell,...]),...]`

### parse.py — Cell[] → PageBudget

セルの構造化パース。純粋関数の合成:

```
Cell[] → CellIndex → classify_all_rows → group_rows_by_moku
  → group_rows_by_setsu → build_*_record → PageBudget
```

**行分類** (`classify_row`):
- `header` — 表ヘッダ行（「目」「千円」「本年度予算額」等のキーワード）
- `moku` — col 0 にテキストあり（目の開始）
- `setsu` — col 9 に `数字 名前` パターン + col 10 に金額
- `sub_item` — col 9 にテキスト + col 10 に金額（節パターンでない）
- `continuation` — col 9 にテキスト、col 10 に金額なし（名前の継続行）
- `setsumei` — col 11 にテキストのみ
- `empty` — 上記いずれでもない

**グルーピング**: `reduce` ベース（mutation なし）で目→節の階層構造を構築。

**説明セル解析**: Word 座標ベースの 3 段パイプライン。
1. `split_words_into_lines` — `Word.y` でセル内の論理行に分割
2. `_parse_setsumei_line` — 各行を `code/name/amount` に分解
3. `fold_setsumei_lines` — `code + name` ラベル位置を正規化して `level` を付与。
   金額あり/なしは同一モデル（`amount: int|None`）で扱う。

これにより、`merge.py` で右表行が統合されても説明の論理行を復元できる。

**列スキーマ**:
| col | 内容 |
|-----|------|
| 0 | 目 |
| 1 | 本年度予算額 |
| 2 | 前年度予算額 |
| 3 | 比較 |
| 4 | 国県支出金 |
| 5 | 地方債 |
| 6 | その他 |
| 7 | 一般財源 |
| 8 | （空き） |
| 9 | 節 区分 |
| 10 | 節 金額 |
| 11 | 説明 |

### flatten.py — PageBudget → FlatRow[]

三つの直交変換:

1. **flatten** (concatMap) — `PageBudget` の木構造をフラットな行に展開
   - `MokuRecord → SetsuRecord → (sub_items | setsumei | setsu_only)` の各リーフが1行
   - orphan_setsu（目なし節）は moku フィールド空欄

2. **ffill** (scanl) — 空欄セルを前行の値で前方充填
   - `MOKU_FIELDS`: moku_name, honendo, zenendo, hikaku, kokuken, chihousei, sonota, ippan
   - `SETSU_FIELDS`: setsu_number, setsu_name, setsu_amount
   - `FFILL_FIELDS = MOKU_FIELDS + SETSU_FIELDS`
   - 汎用的な scanl。ドメイン知識なし。
   - CLI では `rows_ffill` がこの変換のみを担当し、`rows_to_excel` から分離。

3. **label_section** (map) — 款/項を全行に構造的に付与
   - セクション単位で処理されるため ffill 不要。全行に同一の款/項をスタンプ。

**内部フラットヘッダ** (18列):
```
款, 項, 目, 本年度予算額, 前年度予算額, 比較,
国県支出金, 地方債, その他, 一般財源,
節番号, 節名, 節金額, 小区分, 小区分金額,
事業コード, 説明, 説明金額
```

**rows_to_excel の投影（抽出ロジックと非結合）**:
- `wide`: 固定部 `... 事業コード` + 可変部 `説明L1..LN` + `説明金額`
- `long`: 固定部 `... 事業コード` + `説明レベル` + `説明` + `説明金額`

### overlay.py — IO境界（fitz/pymupdf）

デバッグ用。Grid の列/行境界を PDF 上に描画。

---

## セクションベース処理

予算書の構造: **款 → 項 → 目 → 節 → 説明** の階層。
表は (款, 項) 単位で分かれている。ページヘッダに `N款 名前 N項 名前` が記載。

### なぜセクション単位か

- 款/項はページヘッダに記載 → 表データ外
- `rows_ffill` の ffill で伝播すると項境界でリークする
- セクション単位で独立処理 → label_section で構造的に付与 → リーク不可能

### ページ内の項遷移

1ページ内で項が切り替わるケースがある:
```
[row 21] 計 ２款 総務費     ← 小計行（前セクション終了）
[row 23] ２項  徴税費        ← 項遷移行（新セクション開始）
[row 24] 1 税務総務費 ...   ← 新セクションのデータ
```

`section.py: split_page_sections` がこの境界を検出し、
1ページの Cell[] を複数の `(PageHeader, Cell[])` セグメントに分割。

---

## ファイル構成

```
budget_cell/
├── __init__.py        エクスポート（全ドメイン型）
├── types.py           ドメイン型定義（SSOT）
├── pipeline.py        PDF path → section/unit transforms（純粋合成）
├── extract.py         IO: pdfplumber → PageGeometry
├── geometry_normalize.py PageGeometry → PageGeometry（footer artifact 除去）
├── grid.py            PageGeometry → Grid, 歳出フィルタ
├── cells.py           PageGeometry × Grid → Cell[]
├── header.py          PageGeometry × Grid → PageHeader
├── merge.py           Cell[] → Cell[]（行統合）
├── section.py         (PageHeader, Cell[]) → (PageHeader, Cell[])[]（款/項分割）
├── parse.py           Cell[] → PageBudget
├── flatten.py         PageBudget → FlatRow[]
├── row_stream.py      FlatRow ↔ NDJSON adapter
├── excel_io.py        FlatRow ↔ Excel projection（wide/long）
├── overlay.py         IO: Grid → overlay PDF
└── cli/
    ├── excel_to_rows.py     Excel source → NDJSON(FlatRow) stdout
    ├── make_spread.py       PDF → spread PDF
    ├── overlay.py           PDF → overlay PDF パイプライン
    ├── pdf_to_rows.py       PDF path → NDJSON(FlatRow) stdout
    ├── rows_ffill.py        NDJSON stdin → NDJSON stdout（前方充填）
    ├── rows_to_excel.py     NDJSON stdin → Excel sink（wide/long）
    ├── to_excel.py          互換ラッパ（上記3段を同一プロセスで合成）
    ├── comparison_cell.py   年度比較 workbook 生成
    ├── verify_excel.py      FlatRow workbook 契約検証
    └── visualize_geometry.py PDF 幾何可視化

tests/
├── fixtures/
│   ├── r6/
│   │   ├── input/
│   │   │   └── budget-spread.pdf
│   │   └── expected/
│   │       ├── budget-spread-short.xlsx
│   │       └── budget-spread-long.xlsx
│   └── r8/
│       └── expected/
│           └── budget-long-ffill.xlsx
├── test_types.py      型の不変性テスト
├── test_flatten.py    flatten / ffill / label_section テスト
├── test_row_stream.py NDJSON adapter テスト
├── test_excel_io.py   Excel projection テスト
├── test_header.py     ヘッダ抽出テスト
├── test_r6_regression.py R6 fixture 回帰テスト
├── test_section.py    ページ内款/項境界分割テスト
└── test_verify_excel.py workbook 検証CLIテスト
```

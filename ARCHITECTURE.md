# Architecture — budget_cell

富士市一般会計予算書 PDF → 構造化 Excel 変換パイプライン。

## 設計原則

- **不変データ**: 全ドメイン型は `frozen dataclass`。mutation なし。
- **純粋関数パイプライン**: 各モジュールは `f(input) → output` の純粋変換。IO は境界のみ。
- **疎結合**: 各変換ステップは独立。依存は `types.py` のみ共有。
- **関心の分離**: PDF読取 / 幾何構造 / 表解析 / 正規化 / 出力 は完全に分離。

---

## 依存グラフ

```
types.py ← SSOT（全ドメイン型、依存なし）
  ↑
  ├── extract.py    ← IO境界: pdfplumber
  ├── grid.py       ← 純粋: 幾何構造 → Grid
  ├── cells.py      ← 純粋: 幾何構造 × Grid → Cell[]
  ├── header.py     ← 純粋: 幾何構造 × Grid → PageHeader
  ├── merge.py      ← 純粋: Cell[] → Cell[]（複数行統合）
  ├── section.py    ← 純粋: Cell[] → (Header, Cell[])[]（項境界分割）
  ├── parse.py      ← 純粋: Cell[] → PageBudget
  ├── flatten.py    ← 純粋: PageBudget → FlatRow[]
  └── overlay.py    ← IO境界: fitz (pymupdf)

cli/
  ├── to_excel.py   ← パイプライン合成: PDF → Excel
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
SetsumeiEntry(kind: "coded"|"text", code: str|None, name: str, amount: int|None)

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
  setsumei_code, setsumei_name, setsumei_amount          ← 説明
)
```

---

## パイプライン詳細（to_excel.py）

```
PDF (bytes)
 │
 ▼ extract.py: extract_all_geometries
tuple[PageGeometry, ...]                           全ページの幾何情報
 │
 ▼ grid.py: extract_expenditure_pages
tuple[PageGeometry, ...]                           歳出セクションのみ（扉ページ以降の表ページ）
 │
 ▼ grid.py: build_grid  ×  header.py: parse_page_header
tuple[(PageGeometry, Grid, PageHeader|None), ...]  Grid構築 + 表上ヘッダ抽出（並行）
 │
 ▼ filter: header is not None
tuple[(PageHeader, PageGeometry, Grid), ...]       ヘッダのあるデータページのみ
 │
 ▼ cells.py: assign_words_to_cells → merge.py: merge_rows → section.py: split_page_sections
tuple[(PageHeader, tuple[Cell,...]), ...]           セグメント（ページ内の項境界で分割済み）
 │
 ▼ itertools.groupby(key=(kan_number, kan_name, kou_number, kou_name))
dict[(款,項) → tuple[tuple[Cell,...], ...]]         連続セグメントを(款,項)でグループ化
 │
 ▼ 各セクション独立処理: _process_section
 │   ├─ parse.py: parse_page_budget     Cell[] → PageBudget（目/節/説明の構造化）
 │   ├─ flatten.py: flatten_all_pages   PageBudget[] → FlatRow[]（木構造→フラット）
 │   ├─ flatten.py: ffill               FlatRow[] → FlatRow[]（空欄を上から前方充填）
 │   └─ flatten.py: label_section       FlatRow[] → FlatRow[]（款/項を全行に付与）
 │
 ▼ concat all sections
tuple[FlatRow, ...]                                全行
 │
 ▼ _write_excel (openpyxl)
Excel (.xlsx)
```

### 各ステップの変換

| ステップ | 入力型 | 出力型 | モジュール | 性質 |
|---|---|---|---|---|
| PDF読取 | `str (path)` | `tuple[PageGeometry,...]` | extract | IO |
| 歳出フィルタ | `tuple[PageGeometry,...]` | `tuple[PageGeometry,...]` | grid | 純粋 |
| Grid構築 | `PageGeometry` | `Grid` | grid | 純粋 |
| ヘッダ抽出 | `PageGeometry × Grid` | `PageHeader \| None` | header | 純粋 |
| セル割当 | `PageGeometry × Grid` | `tuple[Cell,...]` | cells | 純粋 |
| 行統合 | `tuple[Cell,...]` | `tuple[Cell,...]` | merge | 純粋 |
| 項境界分割 | `PageHeader × tuple[Cell,...]` | `tuple[(PageHeader,tuple[Cell,...]),...]` | section | 純粋 |
| 予算解析 | `tuple[Cell,...]` | `PageBudget` | parse | 純粋 |
| フラット化 | `tuple[PageBudget,...]` | `tuple[FlatRow,...]` | flatten | 純粋 |
| 前方充填 | `tuple[FlatRow,...] × fields` | `tuple[FlatRow,...]` | flatten | 純粋 |
| 款項ラベル | `PageHeader × tuple[FlatRow,...]` | `tuple[FlatRow,...]` | flatten | 純粋 |
| Excel出力 | `tuple[FlatRow,...]` | `.xlsx file` | cli/to_excel | IO |

---

## モジュール詳細

### extract.py — IO境界（pdfplumber）

パッケージ唯一の pdfplumber 依存。PDF バイト列をドメイン型に変換する境界。

- `extract_page_geometry(page) → PageGeometry` — 1ページの幾何情報抽出
- `extract_geometry_from_path(path, page_index=0) → PageGeometry` — 単一ページ
- `extract_all_geometries(path) → tuple[PageGeometry,...]` — 全ページ map

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

### section.py — ページ内の項境界分割

1ページ内に複数の(款,項)セクションが含まれるケースを検出・分割。
小計行（`計 N款 ...`）+ 項遷移行（`N項`）のパターンで境界を判定。

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

**説明セル解析** (`parse_setsumei_cell`): Word の座標位置ベースで
コード（左端3桁）/ 名前（中央）/ 金額（右端）を分離。正規表現より堅牢。

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

3. **label_section** (map) — 款/項を全行に構造的に付与
   - セクション単位で処理されるため ffill 不要。全行に同一の款/項をスタンプ。

**出力ヘッダ** (18列):
```
款, 項, 目, 本年度予算額, 前年度予算額, 比較,
国県支出金, 地方債, その他, 一般財源,
節番号, 節名, 節金額, 小区分, 小区分金額,
事業コード, 説明, 説明金額
```

### overlay.py — IO境界（fitz/pymupdf）

デバッグ用。Grid の列/行境界を PDF 上に描画。

---

## セクションベース処理

予算書の構造: **款 → 項 → 目 → 節 → 説明** の階層。
表は (款, 項) 単位で分かれている。ページヘッダに `N款 名前 N項 名前` が記載。

### なぜセクション単位か

- 款/項はページヘッダに記載 → 表データ外
- ffill で伝播すると項境界でリークする
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
├── extract.py         IO: pdfplumber → PageGeometry
├── grid.py            PageGeometry → Grid, 歳出フィルタ
├── cells.py           PageGeometry × Grid → Cell[]
├── header.py          PageGeometry × Grid → PageHeader
├── merge.py           Cell[] → Cell[]（行統合）
├── section.py         (PageHeader, Cell[]) → (PageHeader, Cell[])[]（項分割）
├── parse.py           Cell[] → PageBudget
├── flatten.py         PageBudget → FlatRow[]
├── overlay.py         IO: Grid → overlay PDF
└── cli/
    ├── to_excel.py    PDF → Excel パイプライン
    └── overlay.py     PDF → overlay PDF パイプライン

tests/
├── test_types.py      型の不変性テスト
├── test_flatten.py    flatten / ffill / label_section テスト
└── test_header.py     ヘッダ抽出テスト
```

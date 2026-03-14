# セッション調査記録 — パイプライン構造分析

## FlatRow の構造

```python
FlatRow(
    # 款/項 — label_section() でスタンプ
    kan_name,        # 款名 ("議会費", "総務費", ...)
    kou_name,        # 項名

    # 目 — 予算書の左表
    moku_name,       # 目名
    honendo,         # 本年度予算額
    zenendo,         # 前年度予算額
    hikaku,          # 比較（本年度 - 前年度）
    kokuken,         # 財源: 国県支出金
    chihousei,       # 財源: 地方債
    sonota,          # 財源: その他
    ippan,           # 財源: 一般財源

    # 節 — 予算書の右表 col 9-10
    setsu_number,    # 節番号
    setsu_name,      # 節名
    setsu_amount,    # 節金額

    # 小区分 — 節の内訳
    sub_item_name,
    sub_item_amount,

    # 説明 — 予算書の右表 col 11
    setsumei_code,   # 事業コード（3桁数字）
    setsumei_level,  # インデントレベル (1=L1, 2=L2, 3=L3)
    setsumei_name,   # 説明名
    setsumei_amount, # 説明金額
    setsumei_path,   # 階層パス ("L1名", "L2名", ...) — parse層で確定
)
```

予算書の階層: 款 → 項 → 目 → 節 → 説明

- 款/項: ページヘッダから抽出（`PageHeader`）
- 目: 左表の主体。財源内訳を持つ
- 節: 右表。目ごとに複数
- 説明: 右表の最右列。インデントで L1/L2/L3 を表現

## parse_page_budget の性質

「1ページ or 1セクション分の表セルを、そのページ内で見える範囲だけで構造化する」関数。

- 入力: 1ページ分の `Cell[]`（merge 済み）
- 出力: `PageBudget` = `(moku_records, orphan_setsu)`
- ページ境界を超えた文脈は持たない → orphan が生まれる

## orphan_setsu

前ページの目に属する節。ページ冒頭に目の行がないまま節が始まるケース。

- parse 時点では目との紐付けがない
- `PageBudget.orphan_setsu` として格納
- flatten 時に `moku=None` で展開 → ffill で前行の目が埋められる

## moku_records

款/項が未紐付けの、目以降の構造。1ページ内で完結する目の木。

```
MokuRecord
  ├── name, honendo, zenendo, hikaku    # 目の基本情報
  ├── zaigen: Zaigen                     # 財源内訳
  └── setsu_list: tuple[SetsuRecord, ...]
        SetsuRecord
          ├── number, name, amount       # 節の基本情報
          ├── sub_items                  # 小区分
          └── setsumei                   # 説明エントリ列
```

## merge.py の右表グループ

```python
_RIGHT_COLS  = frozenset({9, 10, 11})   # 節区分 + 節金額 + 説明
_RIGHT_ANCHOR = frozenset({10})          # 節金額が anchor
```

- col 9（節区分）、col 10（節金額）、col 11（説明）を同一グループとして行結合
- col 10（節金額）を anchor に、anchor のない行は前行に結合
- 左表（col 0-7）とは独立した行境界

## 説明のインデント判定

Word の左端 X 座標をクラスタリングして L1/L2/L3 を決定する。

- `_resolve_level_anchors`: ページ内の説明 Word の x0 座標を収集
- 近接する x0 値をクラスタリング → 小さい順に L1, L2, L3
- ページ単位の計算のため、ページ境界をまたぐ目で結果が変わりうる

## process_pdf_to_excel の4段パイプ（pdf2long.py の main）

```
raw_rows = rows_from_pdf(src)           # 1. 抽出 + parse + flatten
filled   = sectioned_ffill(raw_rows)    # 2. 前方埋め（款/項単位で独立）
paths    = assign_setsumei_paths(filled) # 3. 説明パスの構築
write_rows_to_excel_path(paths, dst)    # 4. Excel 書き出し
```

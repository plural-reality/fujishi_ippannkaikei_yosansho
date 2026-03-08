# budget_cell — Architecture

## Pipeline Overview (Type Signatures)

```haskell
-- ============================================================
-- Layer 0: IO Boundary (extract.py)
-- ============================================================

extract_page_geometry :: pdfplumber.Page -> PageGeometry
--   PageGeometry = { width, height, lines :: [Line], words :: [Word] }
--   Line = { x0, y0, x1, y1, linewidth }
--   Word = { x0, y0, x1, y1, text }


-- ============================================================
-- Layer 1: Grid Construction (grid.py) — pure
-- ============================================================

build_grid :: PageGeometry -> Grid
--   Grid = { col_boundaries :: [Float], row_boundaries :: [Float] }
--
--   col_boundaries: vertical PDF lines の X座標 (確定的, 100%正確)
--   row_boundaries: words の Y座標クラスタリング結果
--                   水平罫線 (table_top, table_bottom) の範囲内に限定
--
--   内部:
--     _vertical_line_xs   :: [Line] -> [Float]
--     _horizontal_line_ys :: [Line] -> [Float]
--     _word_row_ys        :: [Word] -> Float -> [Float]   -- threshold でクラスタリング
--     _cluster_values     :: [Float] -> Float -> [Float]  -- 近傍マージ


-- ============================================================
-- Layer 2: Cell Assignment (cells.py) — pure
-- ============================================================

assign_words_to_cells :: PageGeometry -> Grid -> [Cell]
--   Cell = { row, col, x0, y0, x1, y1, text }
--
--   各 Word の X中点 → col, Y上端 → row にマッピング
--   同一 (row, col) の Word は x0 でソートして空白結合
--   Grid 外の Word は捨てる
--
--   内部:
--     _find_column :: Float -> [Float] -> Int    -- X中点 → col (-1 if outside)
--     _find_row    :: Float -> [Float] -> Int    -- Y上端 → row (-1 if outside)


-- ============================================================
-- Layer 3: Budget Parsing (parse.py) — pure
-- ============================================================

-- 3a. Cell をインデックス化
build_cell_index :: [Cell] -> CellIndex
--   CellIndex = Map (Int, Int) String   -- (row, col) -> text

-- 3b. ヘッダー行検出
detect_header_rows :: [Cell] -> FrozenSet Int
--   _HEADER_TOKENS = {"目", "千円", "節", "本年度予算額", ...}
--   行内のどれかのセルが _HEADER_TOKENS に含まれていれば header

-- 3c. 行分類
classify_row :: CellIndex -> Int -> FrozenSet Int -> RowKind
--   RowKind = "header" | "moku" | "setsu" | "sub_item"
--           | "continuation" | "setsumei" | "empty"
--
--   判定ロジック (優先順):
--     header:       row ∈ header_rows
--     moku:         col[0] (目) にテキストあり
--     setsu:        col[9] (区分) が "N 名前" パターン AND col[10] (金額) あり
--     sub_item:     col[9] あり AND col[10] あり AND 節パターンでない
--     continuation: col[9] あり AND col[10] なし (節名の折り返し)
--     setsumei:     col[11] (説明) にテキストあり
--     empty:        上記いずれでもない

classify_all_rows :: [Cell] -> [(Int, RowKind)]

-- 3d. 目ごとにグルーピング (reduce/scan)
group_rows_by_moku :: [(Int, RowKind)] -> [(Maybe Int, [Int])]
--   header/empty を除外 → "moku" 行で区切り
--   最初の moku より前の行 → orphan (Nothing, rows)
--   moku 行 i 以降 → (Just i, child_rows)

-- 3e. 目の子行を節ごとにグルーピング
group_rows_by_setsu :: CellIndex -> [Int] -> [(Maybe Int, [Int])]
--   _is_setsu で区切り (同じ reduce パターン)

-- 3f. レコード組み立て
build_setsu_record :: CellIndex -> Maybe Int -> [Int] -> SetsuRecord
--   continuation 行をスキップして節名を結合
--   sub_item 行を小区分として収集
--   setsu行 + 子行から説明を収集

build_moku_record :: CellIndex -> Int -> [Int] -> MokuRecord
--   目行から: name, honendo, zenendo, hikaku, zaigen を parse_amount
--   子行を group_rows_by_setsu → map build_setsu_record

-- 3g. トップレベル合成
parse_page_budget :: [Cell] -> PageBudget
--   PageBudget = { moku_records :: [MokuRecord], orphan_setsu :: [SetsuRecord] }
--
--   = build_cell_index
--     >>> classify_all_rows
--     >>> group_rows_by_moku
--     >>> partition (isJust . fst)     -- moku有り / orphan
--     >>> bimap (map build_moku_record) (flatMap (group_rows_by_setsu >>> map build_setsu_record))


-- ============================================================
-- Layer 4: Flatten (flatten.py) — pure
-- ============================================================

flatten_page_budget :: PageBudget -> [FlatRow]
--   orphan_setsu.flatMap(flatten_setsu(Nothing))
--   ++ moku_records.flatMap(flatten_moku)

flatten_moku :: MokuRecord -> [FlatRow]
--   setsu_list.flatMap(flatten_setsu(Just moku))

flatten_setsu :: Maybe MokuRecord -> SetsuRecord -> [FlatRow]
--   sub_items.map(_sub_item_row) ++ setsumei.map(_setsumei_row)
--   空なら _setsu_only_row を1行

row_to_tuple :: FlatRow -> (String, ...)    -- HEADERS 順, None → ""
to_table     :: PageBudget -> [[String]]    -- [HEADERS] ++ map row_to_tuple (flatten_page_budget)
```

## Column Schema (ハードコード)

```
Col  Name         Source         Content
───  ───────────  ─────────     ────────────────────
 0   COL_MOKU     左表           目名 ("11 会計管理費")
 1   COL_HONENDO  左表           本年度予算額
 2   COL_ZENENDO  左表           前年度予算額
 3   COL_HIKAKU   左表           比較増減
 4   COL_KOKUKEN  左表           国県支出金
 5   COL_CHIHOUSEI 左表          地方債
 6   COL_SONOTA   左表           その他
 7   COL_IPPAN    左表           一般財源
 8   (gap)        —              左右表の間の空白列
 9   COL_KUBUN    右表           区分 (節番号+名前, 小区分名)
10   COL_KINGAKU  右表           金額
11   COL_SETSUMEI 右表           説明
```

## Header Detection

ヘッダー行は `_HEADER_TOKENS` との集合積で判定:
```
{"目", "千円", "節", "本年度予算額", "前年度予算額",
 "一般財源", "国県支出金", "地方債", "その他",
 "区分", "金額", "説明", "比較"}
```
行内のどれかのセルがこれらを含めば → header として除外。

## Table Region Detection

`build_grid` 内で水平罫線の min/max から表の上端・下端を推定:
```
table_top    = min(horizontal_line_ys)
table_bottom = max(horizontal_line_ys)
row_boundaries = filter (\y -> table_top - 5 <= y <= table_bottom + 5) (word_row_ys)
```

## 未解決: Cross-Page Context

現在、各ページは独立に処理される。
orphan_setsu は `moku=Nothing` で flatten されるため、目名・予算額が空欄になる。

解決案: `scan` パターン
```haskell
type CarryContext = { last_moku :: Maybe MokuRecord }

flatten_with_context :: CarryContext -> PageBudget -> ([FlatRow], CarryContext)
--   orphan_setsu → last_moku の情報で埋める
--   最後の moku_record を next context として持ち越す

flatten_all_pages :: [PageBudget] -> [FlatRow]
flatten_all_pages = concat . snd . mapAccumL flatten_with_context emptyContext
```

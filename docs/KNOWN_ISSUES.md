# Known Issues

## 課題1: 説明（setsumei）が節（setsu）の子として格納されている

### 現状のデータ構造

```
MokuRecord（目）
  └── setsu_list: tuple[SetsuRecord, ...]
        SetsuRecord（節）
          ├── sub_items     ← 節の子。正しい
          └── setsumei      ← 説明。ここが問題
```

### ドメインの実態（歳出）

- 説明は**目の子**であり、**節とは独立**した関係
- 目 → 節[] と 目 → 説明[] は並列
- 歳入では区分（節に相当）の子だが、歳出では違う

### 影響

- `_moku_level_anchors` で全節を横断して anchor を計算するワークアラウンドが必要になっている
- `_assign_setsumei_paths` も moku スコープで scanl する必要がある
- parse の責務が flatten に漏れている（課題3参照）

---

## 課題2: merge.py で節と説明が同一列グループとして行結合される

### 現状

```python
_RIGHT_COLS = frozenset({9, 10, 11})    # 節区分 + 節金額 + 説明
_RIGHT_ANCHOR = frozenset({10})          # 節金額が anchor
```

col 9（節区分）、col 10（節金額）、col 11（説明）が同一グループで、col 10 を anchor に行結合。

### 問題

- 説明は節と独立した構造を持つのに、節の行境界で説明セルが分断・結合される
- 説明の論理的な行構造が節の物理的な行構造に従属してしまう

### 実際のバグ: 商業振興費（R6, R8 両方）

- 期待: L1: 商業振興費 → L2: 商業振興事務費 → L3: 富士健康印商店会ＴＭＯ事業補助金
- 実際: 全部 L1 として出力される
- 原因が merge の行区切り問題か anchor クラスタリングかは未特定

---

## 課題3: flatten.py に parse の責務（assign_setsumei_paths）が漏れている

### 現状

- `parse.py: _assign_setsumei_paths()` — moku 内で path を構築（正しい位置）
- `flatten.py: assign_setsumei_paths()` — orphan の path を後付け計算（責務の漏れ）

### 原因

- orphan_setsu は parse 時点で moku context を持たない
- ffill で moku が復元された後でないと path が計算できない
- → flatten に parse の仕事（意味の構築）が押し出されている

### flatten の本来の責務

`PageBudget → FlatRow[]` の構造を潰すだけ。意味の構築は parse 層の仕事。

---

## 課題4: setsumei_code の設計

### 現状

- `FlatRow.setsumei_code` は各行の `SetsumeiEntry.code` をそのまま格納
- 各レベル（L1, L2, L3）が独立してコードを持てる
- 独立フィールドとして存在すると「特別な意味がある」と誤解され、依存した実装を生みうる

### 検討事項

- path に吸収する案 → code と path は直交する概念（同じ階層で code が切り替わる）なので単純には統合できない
- 現状維持か、より明確な命名・構造に変えるかは要検討

---

## 課題5: anchor 計算のページ境界不安定

### 症状

同一エントリの `level` が年度間で異なる。

例: "予防広報事業費"
- R6: level=1
- R8: level=2

### 根本原因（推定）

`_resolve_level_anchors` の anchor clustering がページ内の indentation 分布に依存している。
ページ境界をまたぐ目の場合、各ページの word 座標分布が異なるため、
同じ論理エントリでも異なる level に分類される。

### 影響

comparison 層での path 構築は今回の修正（setsumei_path を parse 層で確定）により
level 不整合の影響を受けにくくなったが、long Excel 上の level 値自体は
年度間で不一致のまま。

### 対応予定

別 issue として対応。anchor 計算のページ境界処理を改善する必要がある。

# 富士市予算書データ化プロジェクト

## 概要

富士市の一般会計予算書（PDF）をデータ化し、年度横断で分析可能なCSVを生成するプロジェクトです。

## 処理フロー

```
PDF → 款ごとに分割 → テキスト抽出 → JSON作成 → 年度別JSONをマージ → CSV出力
```

```
R6/bugget.json ─┐
R7/budget.json ─┼→ merge_json_years.py → merged_budget.json → merged_json_to_csv.py → merged_budget.csv
R8/json/_merged.json ─┘
```

## ファイル構成

```
./
├── README.md                     # このファイル
├── split_budget_by_section.py    # PDF分割 + テキスト抽出
├── validate_json.py              # JSONバリデーション
├── merge_json_years.py           # 複数年度JSONのマージ
├── merged_json_to_csv.py         # マージ済みJSON → CSV変換
├── merged_budget.json            # 年度統合JSON（生成物）
├── merged_budget.csv             # 年度統合CSV（最終成果物）
├── sample_歳入.json              # JSON形式のサンプル
│
└── Rn/                           # 年度別フォルダ（R6/, R7/, R8/）
    ├── bugget.pdf                # 予算の元データ
    ├── 分割/                     # 款ごとに分割されたファイル
    │   ├── 00_概要.pdf, .txt
    │   ├── 歳入_01款_市税.pdf, .txt
    │   └── ...
    └── json/                     # 款別JSON + 統合JSON
        ├── 歳入_01款_市税.json
        ├── 歳出_01款_議会費.json
        └── _merged.json          # 年度内統合版
```

## 作業手順

### Step 1: PDF分割とテキスト抽出

```bash
# ghostscriptをインストール
brew install ghostscript

# 款ごとに分割
python split_budget_by_section.py Rn/bugget.pdf Rn/分割 --workers 8
```

### Step 2: JSON作成

分割したテキストからJSONを作成します（AI活用推奨）。

```bash
# バリデーション実行
python validate_json.py Rn/json/*.json

# 統合ファイル作成後もバリデーション
python validate_json.py Rn/json/_merged.json
```

### Step 3: 年度統合JSONの生成

```bash
python merge_json_years.py
```

入力: 各年度の統合JSON（R6/bugget.json, R7/budget.json, R8/json/_merged.json）
出力: `merged_budget.json`

処理内容:
- 各年度のJSONを読み込み
- 金額単位を千円に統一（R6は円単位なので÷1000）
- 款→項→目→節の階層でマッチングしてマージ
- 年度別フィールド（R6, R7, R8）に変換

### Step 4: CSV生成

```bash
python merged_json_to_csv.py
```

入力: `merged_budget.json`
出力: `merged_budget.csv`

CSV形式:
```csv
款,項,目,節,説明,R6,R7,R8,補足_R6,補足_R7,補足_R8
市税,,,,,46460600,48352400,49286300,,,
,市民税,,,,16739000,18420900,18719000,,,
```

## JSON形式

### 個別款ファイル（例: 歳入_01款_市税.json）

```json
{
  "市税": {
    "本年度予算額": 49286300,
    "前年度予算額": 48352500,
    "項": [
      {
        "市民税": {
          "本年度予算額": 18719000,
          "目": [
            {
              "個人": {
                "本年度予算額": 16203500,
                "節": [
                  {
                    "現年課税分": {
                      "金額": 16084000,
                      "説明": {
                        "均等割": {
                          "金額": 399000,
                          "調定見込額": "404000*98.9%"
                        }
                      }
                    }
                  }
                ]
              }
            }
          ]
        }
      }
    ]
  }
}
```

### 必須フィールド

| レベル | 必須フィールド |
|--------|---------------|
| 款 | `本年度予算額`, `項` |
| 項 | `本年度予算額`, `目` |
| 目 | `本年度予算額` |
| 節 | `金額` |

## 注意点

1. **CSVは編集しない**: JSONを編集し、CSVはプログラムで生成
2. **計算式はテキスト**: `"調定見込額": "408000*98.9%"`
3. **金額は千円単位の整数**: カンマなし

## データソース

富士市: https://www.city.fuji.shizuoka.jp/

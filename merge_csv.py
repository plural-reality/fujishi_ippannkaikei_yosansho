#!/usr/bin/env python3
"""
富士市予算書 CSV マージツール

各年度ディレクトリにあるCSVファイルを統合し、
年度横断で予算を比較できるマージ済みCSVを生成する。

Merge.md の注意点に従い:
1. Rn年度のCSVには Rn(案) と R(n-1)(確定) が含まれる
2. 同じ年度でも「案」と「確定」は別データとして保存
3. 年度によって予算項目が増減するため、カラムは動的に追加
4. 記載のなかった年度は0として扱う
"""

import csv
import os
import re
from pathlib import Path
from collections import OrderedDict
from typing import Dict, List, Tuple, Set


def normalize_item_name(name: str) -> str:
    """
    項目名を正規化
    - 全角スペースと半角スペースを除去
    - 類似文字の統一
    """
    if not name:
        return ''

    # スペースを除去（項目名内のスペースは不要）
    result = re.sub(r'[\s　]+', '', name)

    return result


def split_description(desc: str) -> Tuple[str, str]:
    """
    説明を「項目名」と「補足」に分離

    例:
    - "均等割（調定見込額 402,000×98.9％）" → ("均等割", "調定見込額 402,000×98.9％")
    - "現年課税分" → ("現年課税分", "")
    - "調定見込額 350,700×33.3％" → ("", "調定見込額 350,700×33.3％")  # 補足のみの場合
    """
    if not desc:
        return ('', '')

    # 括弧のパターン: （）または ()
    # 最初の括弧で分割
    match = re.match(r'^([^（(]*)[（(](.+)[）)]$', desc.strip())
    if match:
        item_name = normalize_item_name(match.group(1).strip())
        supplement = match.group(2).strip()
        return (item_name, supplement)

    # 「備考」で始まる場合は補足扱い
    if desc.strip().startswith('備考'):
        return ('', desc.strip())

    # 「調定見込額」で始まる場合は補足扱い
    if desc.strip().startswith('調定見込額'):
        return ('', desc.strip())

    # それ以外は項目名のみ（正規化）
    return (normalize_item_name(desc.strip()), '')


def normalize_key(row: Dict[str, str]) -> str:
    """
    予算項目の階層キーを生成
    款-項-目-節-説明(項目名のみ) の組み合わせをキーとする
    補足部分は除外してキーを生成
    """
    parts = []
    for col in ['款', '項', '目', '節']:
        val = row.get(col, '').strip()
        parts.append(val if val else '')

    # 説明は項目名のみ使用
    desc = row.get('説明', '').strip()
    item_name, _ = split_description(desc)
    parts.append(item_name)

    return '|'.join(parts)


def get_hierarchy_level(row: Dict[str, str]) -> int:
    """
    階層レベルを取得
    0: 款のみ
    1: 款-項
    2: 款-項-目
    3: 款-項-目-節
    4: 款-項-目-節-説明
    """
    levels = ['款', '項', '目', '節', '説明']
    level = -1
    for i, col in enumerate(levels):
        if row.get(col, '').strip():
            level = i
    return level


def parse_csv_file(filepath: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    CSVファイルを読み込み、ヘッダーとデータ行を返す
    階層構造を復元：空のセルには直前の親値を継承する
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = []

        # 階層の現在値を保持
        current_hierarchy = {'款': '', '項': '', '目': '', '節': ''}
        hierarchy_cols = ['款', '項', '目', '節']

        for row in reader:
            new_row = dict(row)

            # 階層を復元
            for i, col in enumerate(hierarchy_cols):
                val = row.get(col, '').strip()
                if val:
                    # この階層に値がある場合、更新
                    current_hierarchy[col] = val
                    # 下位の階層をリセット
                    for j in range(i + 1, len(hierarchy_cols)):
                        current_hierarchy[hierarchy_cols[j]] = ''
                else:
                    # 空の場合、親の値を継承
                    new_row[col] = current_hierarchy[col]

            rows.append(new_row)

    return headers, rows


def extract_fiscal_years_from_headers(headers: List[str]) -> List[str]:
    """
    ヘッダーから年度カラム（R5, R6, R7, R8など）を抽出
    """
    year_pattern = re.compile(r'^R\d+$')
    return [h for h in headers if year_pattern.match(h)]


def determine_year_types(csv_dir_year: int, year_columns: List[str]) -> Dict[str, str]:
    """
    各年度カラムが「案」か「確定」かを判定

    Rn年度のPDF（CSVの元）には:
    - Rn年度の予算案
    - R(n-1)年度の予算（確定済み）
    が記載されている
    """
    year_types = {}
    for col in year_columns:
        col_year = int(col[1:])  # "R7" -> 7
        if col_year == csv_dir_year:
            year_types[col] = f"{col}(案)"
        elif col_year == csv_dir_year - 1:
            year_types[col] = f"{col}(確定)"
        else:
            # 想定外のケース
            year_types[col] = f"{col}(不明)"
    return year_types


def load_all_csvs() -> Dict[str, Tuple[List[str], List[Dict[str, str]], int]]:
    """
    全ての年度CSVを読み込む
    戻り値: {ファイルパス: (ヘッダー, データ行, 年度)}
    """
    base_dir = Path(__file__).parent
    csv_files = {}

    # 各年度ディレクトリをスキャン
    for year_dir in sorted(base_dir.glob('R*')):
        if not year_dir.is_dir():
            continue

        dir_year_match = re.match(r'R(\d+)', year_dir.name)
        if not dir_year_match:
            continue

        dir_year = int(dir_year_match.group(1))

        # budget.csv または *予算*.csv を探す
        csv_candidates = list(year_dir.glob('budget.csv')) + list(year_dir.glob('*予算*.csv'))

        for csv_path in csv_candidates:
            # 重複を避ける（budget.csvを優先）
            if str(year_dir) in [str(Path(k).parent) for k in csv_files]:
                if csv_path.name != 'budget.csv':
                    continue

            try:
                headers, rows = parse_csv_file(str(csv_path))
                csv_files[str(csv_path)] = (headers, rows, dir_year)
                print(f"読み込み: {csv_path.name} (R{dir_year}年度)")
            except Exception as e:
                print(f"エラー: {csv_path} の読み込みに失敗 - {e}")

    return csv_files


def merge_all_data(csv_data: Dict[str, Tuple[List[str], List[Dict[str, str]], int]]) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    """
    全てのCSVデータをマージ

    戻り値: (全年度カラムリスト, {キー: {年度カラム: 値}})
    """
    # 全ての年度カラムを収集
    all_year_columns: Set[str] = set()

    # 全データを格納
    merged_data: Dict[str, Dict[str, str]] = OrderedDict()

    # キーの出現順序を記録（階層構造を維持するため）
    key_order: List[str] = []

    for filepath, (headers, rows, dir_year) in sorted(csv_data.items(), key=lambda x: x[1][2]):
        year_columns = extract_fiscal_years_from_headers(headers)
        year_types = determine_year_types(dir_year, year_columns)

        print(f"\n処理中: {Path(filepath).name}")
        print(f"  年度カラム: {year_columns}")
        print(f"  タイプ判定: {year_types}")

        for typed_col in year_types.values():
            all_year_columns.add(typed_col)

        for row in rows:
            key = normalize_key(row)
            desc = row.get('説明', '').strip()
            item_name, supplement = split_description(desc)

            if key not in merged_data:
                merged_data[key] = {
                    '款': row.get('款', ''),
                    '項': row.get('項', ''),
                    '目': row.get('目', ''),
                    '節': row.get('節', ''),
                    '説明': item_name,  # 項目名のみ
                    '補足': {},  # 年度別の補足を格納
                }
                key_order.append(key)

            # 補足を年度別に保存
            if supplement:
                for orig_col, typed_col in year_types.items():
                    if typed_col not in merged_data[key]['補足']:
                        merged_data[key]['補足'][typed_col] = supplement

            # 年度データを追加
            for orig_col, typed_col in year_types.items():
                value = row.get(orig_col, '').strip()
                if value:
                    # 既存の値がある場合は上書きしない（最初に見つかった値を優先）
                    if typed_col not in merged_data[key] or not merged_data[key][typed_col]:
                        merged_data[key][typed_col] = value

    # 年度カラムをソート（R5(確定), R5(案), R6(確定), R6(案), ...の順）
    def sort_year_col(col: str) -> Tuple[int, int]:
        match = re.match(r'R(\d+)\((案|確定|不明)\)', col)
        if match:
            year = int(match.group(1))
            type_order = {'確定': 0, '案': 1, '不明': 2}
            return (year, type_order.get(match.group(2), 3))
        return (999, 0)

    sorted_year_columns = sorted(all_year_columns, key=sort_year_col)

    # キーの順序を維持したまま新しいOrderedDictを作成
    ordered_merged = OrderedDict()
    for key in key_order:
        if key in merged_data:
            ordered_merged[key] = merged_data[key]
            del merged_data[key]  # 処理済みを削除

    # 残りを追加（通常はないはず）
    for key, data in merged_data.items():
        ordered_merged[key] = data

    return sorted_year_columns, ordered_merged


def write_merged_csv(year_columns: List[str], data: Dict[str, Dict[str, str]], output_path: str):
    """
    マージ済みデータをCSVに出力
    """
    base_columns = ['款', '項', '目', '節', '説明']
    # 補足カラムを年度別に追加
    supplement_columns = [f'補足_{col}' for col in year_columns]
    all_columns = base_columns + year_columns + supplement_columns

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(all_columns)

        for key, row_data in data.items():
            row = []
            for col in base_columns:
                value = row_data.get(col, '')
                row.append(value)

            # 年度データ
            for col in year_columns:
                value = row_data.get(col, '')
                row.append(value)

            # 補足データ（年度別）
            supplements = row_data.get('補足', {})
            for col in year_columns:
                value = supplements.get(col, '')
                row.append(value)

            writer.writerow(row)

    print(f"\n出力完了: {output_path}")
    print(f"  総行数: {len(data)}")
    print(f"  カラム: {all_columns}")


def main():
    print("=" * 60)
    print("富士市予算書 CSV マージツール")
    print("=" * 60)

    # 全CSVを読み込み
    csv_data = load_all_csvs()

    if not csv_data:
        print("エラー: 読み込めるCSVファイルがありませんでした")
        return

    # マージ実行
    year_columns, merged_data = merge_all_data(csv_data)

    # 出力
    output_path = Path(__file__).parent / 'merged_budget.csv'
    write_merged_csv(year_columns, merged_data, str(output_path))

    print("\n" + "=" * 60)
    print("マージ完了")
    print("=" * 60)


if __name__ == '__main__':
    main()

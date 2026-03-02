#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
富士市予算書 マージ済みJSON → CSV コンバーター

merge_json_years.pyで生成した統合JSONを読み込み、
年度横断で比較できるCSVを生成する。

使い方:
  python3 merged_json_to_csv.py
  python3 merged_json_to_csv.py merged_budget.json output.csv
"""

import json
import csv
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


def extract_name_and_data(obj: dict) -> tuple:
    """{"市税": {...}} → ("市税", {...})"""
    for key in obj.keys():
        if not key.startswith("_"):  # _metaなどを除外
            return key, obj[key]
    return None, None


def get_years_from_data(data: dict) -> List[str]:
    """JSONからマージ対象の年度リストを取得"""
    if "_meta" in data and "years" in data["_meta"]:
        return data["_meta"]["years"]
    # フォールバック: データから推測
    return ["R6", "R7", "R8"]


def convert_to_csv_rows(data: dict) -> tuple:
    """
    統合JSONをCSV行リストに変換

    戻り値: (headers, rows)
    """
    years = get_years_from_data(data)
    base_headers = ["款", "項", "目", "節", "説明"]
    supplement_headers = [f"補足_{year}" for year in years]
    headers = base_headers + years + supplement_headers

    rows = []

    for section_key in ["歳入", "歳出"]:
        section = data.get(section_key)
        if not section:
            continue

        kan_list = section.get("款", [])

        for kan_obj in kan_list:
            kan_name, kan_data = extract_name_and_data(kan_obj)
            if kan_name is None:
                continue

            # 款行
            row = [kan_name, "", "", "", ""]
            for year in years:
                row.append(kan_data.get(year, ""))
            for _ in years:
                row.append("")  # 補足は空
            rows.append(row)

            # 項
            for kou_obj in kan_data.get("項", []):
                kou_name, kou_data = extract_name_and_data(kou_obj)
                if kou_name is None:
                    continue

                row = ["", kou_name, "", "", ""]
                for year in years:
                    row.append(kou_data.get(year, ""))
                for _ in years:
                    row.append("")
                rows.append(row)

                # 目
                for moku_obj in kou_data.get("目", []):
                    moku_name, moku_data = extract_name_and_data(moku_obj)
                    if moku_name is None:
                        continue

                    row = ["", "", moku_name, "", ""]
                    for year in years:
                        row.append(moku_data.get(year, ""))
                    for _ in years:
                        row.append("")
                    rows.append(row)

                    # 節
                    for setsu_obj in moku_data.get("節", []):
                        setsu_name, setsu_data = extract_name_and_data(setsu_obj)
                        if setsu_name is None:
                            continue

                        row = ["", "", "", setsu_name, ""]
                        for year in years:
                            row.append(setsu_data.get(year, ""))
                        for _ in years:
                            row.append("")
                        rows.append(row)

                        # 説明
                        setsumei = setsu_data.get("説明", {})
                        if isinstance(setsumei, dict):
                            for desc_name, desc_data in setsumei.items():
                                row = ["", "", "", "", desc_name]

                                for year in years:
                                    if isinstance(desc_data, dict):
                                        row.append(desc_data.get(year, ""))
                                    else:
                                        row.append("")

                                # 補足情報
                                for year in years:
                                    if isinstance(desc_data, dict):
                                        hosoku = desc_data.get("補足", {})
                                        if year in hosoku:
                                            year_hosoku = hosoku[year]
                                            if isinstance(year_hosoku, dict):
                                                hosoku_str = ", ".join(f"{k}: {v}" for k, v in year_hosoku.items())
                                                row.append(hosoku_str)
                                            else:
                                                row.append(str(year_hosoku))
                                        else:
                                            row.append("")
                                    else:
                                        row.append("")

                                rows.append(row)

    return headers, rows


def main():
    base_dir = Path(__file__).parent

    if len(sys.argv) >= 2:
        input_path = Path(sys.argv[1])
    else:
        input_path = base_dir / "merged_budget.json"

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        output_path = base_dir / "merged_budget.csv"

    if not input_path.exists():
        print(f"エラー: {input_path} が見つかりません")
        print("先に merge_json_years.py を実行してください")
        sys.exit(1)

    print(f"読み込み: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    headers, rows = convert_to_csv_rows(data)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)

    print(f"出力完了: {output_path}")
    print(f"  ヘッダー: {headers}")
    print(f"  行数: {len(rows)}")


if __name__ == "__main__":
    main()

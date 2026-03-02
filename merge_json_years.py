#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
富士市予算書 複数年度JSONマージツール

各年度の統合JSONを読み込み、年度横断で比較できる統合JSONを生成する。

使い方:
  python3 merge_json_years.py
  python3 merge_json_years.py -o output.json
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import OrderedDict
import argparse


def extract_name_and_data(obj: dict) -> tuple:
    """{"市税": {...}} → ("市税", {...})"""
    key = next(k for k in obj.keys())
    return key, obj[key]


def normalize_amount(value: Any, year: str) -> Optional[int]:
    """金額を千円単位に正規化（R6は円単位なので÷1000）"""
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        return None

    # R6は円単位（10桁以上の数値）なので÷1000
    # R7/R8は千円単位（8桁程度の数値）
    if year == "R6" and value > 100000000:  # 1億以上なら円単位と判断
        return int(value // 1000)
    return int(value)


def normalize_setsumei(setsumei: Any) -> dict:
    """
    説明を辞書形式に正規化

    R6形式（リスト）:
      [{"区分": "土地", "金額": 8144000000}, ...]

    R7/R8形式（辞書）:
      {"土地": {"金額": 8136000, "調定見込額": "..."}, ...}
    """
    if setsumei is None:
        return {}

    if isinstance(setsumei, dict):
        return setsumei

    if isinstance(setsumei, list):
        result = {}
        for item in setsumei:
            if isinstance(item, dict):
                # キーを探す: 区分, 項目, 名称, 名, 事業名
                name = None
                for name_key in ["区分", "項目", "名称", "名", "事業名"]:
                    if name_key in item:
                        name = item[name_key]
                        break

                if name:
                    data = {k: v for k, v in item.items() if k not in ["区分", "項目", "名称", "名", "事業名"]}
                    result[name] = data
        return result

    return {}


def create_merged_node(years: List[str]) -> dict:
    """マージ用の空ノードを作成"""
    node = OrderedDict()
    for year in years:
        node[year] = None
    return node


def merge_kan_list(kan_lists: Dict[str, List], years: List[str]) -> List:
    """款リストをマージ"""
    merged_kans = OrderedDict()

    for year in years:
        kan_list = kan_lists.get(year, [])
        for kan_obj in kan_list:
            kan_name, kan_data = extract_name_and_data(kan_obj)

            if kan_name not in merged_kans:
                merged_kans[kan_name] = create_merged_node(years)
                merged_kans[kan_name]["項"] = OrderedDict()

            # 本年度予算額を年度別に保存
            amount = kan_data.get("本年度予算額")
            merged_kans[kan_name][year] = normalize_amount(amount, year)

            # 項をマージ
            kou_list = kan_data.get("項", [])
            for kou_obj in kou_list:
                kou_name, kou_data = extract_name_and_data(kou_obj)

                if kou_name not in merged_kans[kan_name]["項"]:
                    merged_kans[kan_name]["項"][kou_name] = create_merged_node(years)
                    merged_kans[kan_name]["項"][kou_name]["目"] = OrderedDict()

                amount = kou_data.get("本年度予算額")
                merged_kans[kan_name]["項"][kou_name][year] = normalize_amount(amount, year)

                # 目をマージ
                moku_list = kou_data.get("目", [])
                for moku_obj in moku_list:
                    moku_name, moku_data = extract_name_and_data(moku_obj)

                    if moku_name not in merged_kans[kan_name]["項"][kou_name]["目"]:
                        merged_kans[kan_name]["項"][kou_name]["目"][moku_name] = create_merged_node(years)
                        merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"] = OrderedDict()

                    amount = moku_data.get("本年度予算額")
                    merged_kans[kan_name]["項"][kou_name]["目"][moku_name][year] = normalize_amount(amount, year)

                    # 節をマージ
                    setsu_list = moku_data.get("節", [])
                    for setsu_obj in setsu_list:
                        setsu_name, setsu_data = extract_name_and_data(setsu_obj)

                        if setsu_name not in merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"]:
                            merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name] = create_merged_node(years)
                            merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"] = OrderedDict()

                        amount = setsu_data.get("金額")
                        merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name][year] = normalize_amount(amount, year)

                        # 説明をマージ
                        setsumei = setsu_data.get("説明", {})
                        setsumei_normalized = normalize_setsumei(setsumei)

                        for desc_name, desc_data in setsumei_normalized.items():
                            if desc_name not in merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"]:
                                merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"][desc_name] = create_merged_node(years)
                                merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"][desc_name]["補足"] = {}

                            if isinstance(desc_data, dict):
                                amount = desc_data.get("金額")
                                merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"][desc_name][year] = normalize_amount(amount, year)

                                # 補足情報（調定見込額など）
                                for k, v in desc_data.items():
                                    if k != "金額":
                                        if year not in merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"][desc_name]["補足"]:
                                            merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"][desc_name]["補足"][year] = {}
                                        merged_kans[kan_name]["項"][kou_name]["目"][moku_name]["節"][setsu_name]["説明"][desc_name]["補足"][year][k] = v

    # OrderedDictをリスト形式に変換
    return convert_to_list_format(merged_kans, years)


def convert_to_list_format(merged_data: OrderedDict, years: List[str]) -> List:
    """OrderedDictをリスト形式に変換"""
    result = []

    for kan_name, kan_data in merged_data.items():
        kan_obj = OrderedDict()
        kan_obj[kan_name] = OrderedDict()

        # 年度別金額
        for year in years:
            kan_obj[kan_name][year] = kan_data.get(year)

        # 項
        if "項" in kan_data and kan_data["項"]:
            kan_obj[kan_name]["項"] = []
            for kou_name, kou_data in kan_data["項"].items():
                kou_obj = OrderedDict()
                kou_obj[kou_name] = OrderedDict()

                for year in years:
                    kou_obj[kou_name][year] = kou_data.get(year)

                # 目
                if "目" in kou_data and kou_data["目"]:
                    kou_obj[kou_name]["目"] = []
                    for moku_name, moku_data in kou_data["目"].items():
                        moku_obj = OrderedDict()
                        moku_obj[moku_name] = OrderedDict()

                        for year in years:
                            moku_obj[moku_name][year] = moku_data.get(year)

                        # 節
                        if "節" in moku_data and moku_data["節"]:
                            moku_obj[moku_name]["節"] = []
                            for setsu_name, setsu_data in moku_data["節"].items():
                                setsu_obj = OrderedDict()
                                setsu_obj[setsu_name] = OrderedDict()

                                for year in years:
                                    setsu_obj[setsu_name][year] = setsu_data.get(year)

                                # 説明
                                if "説明" in setsu_data and setsu_data["説明"]:
                                    setsu_obj[setsu_name]["説明"] = OrderedDict()
                                    for desc_name, desc_data in setsu_data["説明"].items():
                                        setsu_obj[setsu_name]["説明"][desc_name] = OrderedDict()

                                        for year in years:
                                            setsu_obj[setsu_name]["説明"][desc_name][year] = desc_data.get(year)

                                        if "補足" in desc_data and desc_data["補足"]:
                                            setsu_obj[setsu_name]["説明"][desc_name]["補足"] = desc_data["補足"]

                                moku_obj[moku_name]["節"].append(setsu_obj)

                        kou_obj[kou_name]["目"].append(moku_obj)

                kan_obj[kan_name]["項"].append(kou_obj)

        result.append(kan_obj)

    return result


def load_budget_json(filepath: Path, year: str) -> dict:
    """予算JSONを読み込み"""
    print(f"読み込み: {filepath} ({year})")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_all_years(base_dir: Path) -> dict:
    """全年度のJSONをマージ"""
    # 年度とファイルのマッピング
    year_files = {
        "R6": base_dir / "R6" / "bugget.json",
        "R7": base_dir / "R7" / "budget.json",
        "R8": base_dir / "R8" / "json" / "_merged.json",
    }

    years = []
    data_by_year = {}

    for year, filepath in year_files.items():
        if filepath.exists():
            data_by_year[year] = load_budget_json(filepath, year)
            years.append(year)
        else:
            print(f"スキップ: {filepath} (存在しない)")

    if not years:
        raise ValueError("読み込めるJSONファイルがありません")

    years.sort()  # R6, R7, R8の順

    # 歳入・歳出それぞれをマージ
    result = OrderedDict()

    for section in ["歳入", "歳出"]:
        kan_lists = {}
        for year in years:
            if section in data_by_year[year]:
                kan_lists[year] = data_by_year[year][section].get("款", [])

        if kan_lists:
            result[section] = {
                "款": merge_kan_list(kan_lists, years)
            }

    # メタ情報を追加
    result["_meta"] = {
        "years": years,
        "generated_from": [str(year_files[y]) for y in years if year_files[y].exists()]
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="複数年度の予算JSONをマージ")
    parser.add_argument("-o", "--output", default="merged_budget.json", help="出力ファイル名")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    output_path = base_dir / args.output

    print("=" * 60)
    print("富士市予算書 複数年度JSONマージツール")
    print("=" * 60)

    merged_data = merge_all_years(base_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    years = merged_data.get("_meta", {}).get("years", [])
    print(f"\n出力完了: {output_path}")
    print(f"  年度: {', '.join(years)}")

    # 簡易統計
    for section in ["歳入", "歳出"]:
        if section in merged_data:
            kan_count = len(merged_data[section].get("款", []))
            print(f"  {section}: {kan_count}款")


if __name__ == "__main__":
    main()

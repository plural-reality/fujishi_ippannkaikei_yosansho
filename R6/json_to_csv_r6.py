#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R6予算書 JSON → CSV コンバーター
金額を千円単位に変換し、R5/R6列として出力
"""

import json
import csv
import sys


def extract_name_and_data(obj):
    """{"市税": {...}} → ("市税", {...})"""
    key = next(k for k in obj.keys())
    return key, obj[key]


def to_sen(value):
    """円単位を千円単位に変換（整数）"""
    if value is None or value == "":
        return ""
    if isinstance(value, int):
        return value // 1000
    return value


def is_sub_item(value):
    """説明の値が子項目（dict with 金額）かどうか"""
    return isinstance(value, dict) and "金額" in value


def process_setsumei(setsumei, rows):
    """説明を処理。子項目があれば説明行を追加。"""
    for key, val in setsumei.items():
        if is_sub_item(val):
            extras = {k: v for k, v in val.items() if k != "金額"}
            if extras:
                note = "、".join(f"{k} {v}" for k, v in extras.items())
                desc = f"{key}（{note}）"
            else:
                desc = key
            rows.append(["", "", "", "", desc, "", to_sen(val["金額"])])


def flat_notes(setsumei):
    """説明から備考文字列を生成（子項目がない場合）"""
    if not isinstance(setsumei, dict):
        return ""
    notes = []
    for key, val in setsumei.items():
        if isinstance(val, str):
            notes.append(f"{key} {val}")
        elif isinstance(val, (int, float)):
            notes.append(f"{key} {val}")
    return "、".join(notes) if notes else ""


def has_named_sub_items(setsumei):
    """説明に名前付き子項目（金額あり dict）があるか"""
    if isinstance(setsumei, dict):
        return any(is_sub_item(v) for v in setsumei.values())
    return False


def convert(data):
    rows = []

    for section_key in ["歳入", "歳出"]:
        section = data.get(section_key)
        if not section:
            continue

        kan_list = section.get("款", [])

        for kan_obj in kan_list:
            kan_name, kan_data = extract_name_and_data(kan_obj)
            rows.append([
                kan_name, "", "", "", "",
                to_sen(kan_data.get("前年度予算額")),
                to_sen(kan_data.get("本年度予算額")),
            ])

            for kou_obj in kan_data.get("項", []):
                kou_name, kou_data = extract_name_and_data(kou_obj)
                rows.append([
                    "", kou_name, "", "", "",
                    to_sen(kou_data.get("前年度予算額")),
                    to_sen(kou_data.get("本年度予算額")),
                ])

                for moku_obj in kou_data.get("目", []):
                    moku_name, moku_data = extract_name_and_data(moku_obj)
                    rows.append([
                        "", "", moku_name, "", "",
                        to_sen(moku_data.get("前年度予算額")),
                        to_sen(moku_data.get("本年度予算額")),
                    ])

                    for setsu_obj in moku_data.get("節", []):
                        setsu_name, setsu_data = extract_name_and_data(setsu_obj)
                        amount = to_sen(setsu_data.get("金額"))
                        setsumei = setsu_data.get("説明", {})

                        if has_named_sub_items(setsumei):
                            rows.append(["", "", "", setsu_name, "", "", amount])
                            process_setsumei(setsumei, rows)
                        else:
                            notes = flat_notes(setsumei)
                            rows.append(["", "", "", setsu_name, notes, "", amount])
    return rows


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 json_to_csv_r6.py input.json [output.csv]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    rows = convert(data)

    if len(sys.argv) >= 3:
        out = open(sys.argv[2], "w", encoding="utf-8", newline="")
    else:
        out = sys.stdout

    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["款", "項", "目", "節", "説明", "R5", "R6"])
    for row in rows:
        writer.writerow(row)

    if out is not sys.stdout:
        out.close()
        print(f"出力: {sys.argv[2]} ({len(rows)}行)", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
予算書テーブル結合スクリプト（セルレベル座標対応版）

セルレベルのbbox情報を使用して、左右テーブルを1対多の関係で正確に紐付け。
"""

import sys
import json
import csv
import math
from pathlib import Path
from dataclasses import dataclass, field


def clean_value(val):
    """NaN/None/infを空文字に変換"""
    if val is None:
        return ""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return ""
    return val


def classify_tables(tables: list[dict]) -> tuple[list[dict], list[dict]]:
    """テーブルをX座標で左右に分類"""
    left_tables = []
    right_tables = []

    for t in tables:
        if t["bbox"]["x1"] < 1100:
            left_tables.append(t)
        elif t["bbox"]["x1"] > 1200:
            right_tables.append(t)

    left_tables.sort(key=lambda t: t["bbox"]["y1"])
    right_tables.sort(key=lambda t: t["bbox"]["y1"])

    return left_tables, right_tables


def pair_tables_by_y(left_tables: list[dict], right_tables: list[dict], threshold: int = 300):
    """Y座標でテーブルをペアリング"""
    pairs = []
    used_right = set()

    for left in left_tables:
        best_match = None
        best_diff = float('inf')

        for i, right in enumerate(right_tables):
            if i in used_right:
                continue
            diff = abs(left["bbox"]["y1"] - right["bbox"]["y1"])
            if diff < threshold and diff < best_diff:
                best_diff = diff
                best_match = (i, right)

        if best_match:
            used_right.add(best_match[0])
            pairs.append((left, best_match[1]))
        else:
            pairs.append((left, None))

    for i, right in enumerate(right_tables):
        if i not in used_right:
            pairs.append((None, right))

    return pairs


def get_row_y_range_from_cells(cells_row: list[dict]) -> tuple[int, int] | None:
    """セル行からY範囲を取得"""
    y1_vals = []
    y2_vals = []
    for cell in cells_row:
        if cell and cell.get("bbox"):
            y1_vals.append(cell["bbox"]["y1"])
            y2_vals.append(cell["bbox"]["y2"])

    if y1_vals and y2_vals:
        return (min(y1_vals), max(y2_vals))
    return None


def is_header_row(row_data: list, row_idx: int) -> bool:
    """ヘッダー行かどうかを判定"""
    if not row_data:
        return True

    first_val = clean_value(row_data[0]) if row_data else ""

    # 明確なヘッダー文字列
    header_keywords = ["目", "節", "区分", "区\n分", "金額", "金\n額", "説明", "説\n明",
                       "本年度予算額", "前年度予算額", "比較", "比\n較"]

    if first_val in header_keywords:
        return True

    # 「千円」だけの行もヘッダー
    values = [clean_value(v) for v in row_data if v]
    if all(v in ["千円", ""] for v in values):
        return True

    return False


def build_parent_child_structure_with_cells(left: dict | None, right: dict | None, page_num: int, table_idx: int) -> list[dict]:
    """
    セルレベルのbbox情報を使って親子構造を構築
    """
    if left is None and right is None:
        return []

    records = []

    # 左テーブルの各行をY範囲付きで取得
    left_rows = []
    if left and "cells" in left:
        for row_idx, cells_row in enumerate(left["cells"]):
            y_range = get_row_y_range_from_cells(cells_row)
            row_data = left["data"][row_idx] if row_idx < len(left["data"]) else []

            # ヘッダー行はスキップ
            if is_header_row(row_data, row_idx):
                continue

            left_rows.append({
                "row_idx": row_idx,
                "y_range": y_range,
                "data": row_data,
                "children": []
            })

    # 右テーブルの各行をY中心座標付きで取得
    right_rows = []
    if right and "cells" in right:
        for row_idx, cells_row in enumerate(right["cells"]):
            y_range = get_row_y_range_from_cells(cells_row)
            row_data = right["data"][row_idx] if row_idx < len(right["data"]) else []

            # ヘッダー行はスキップ
            if is_header_row(row_data, row_idx):
                continue

            if y_range:
                y_center = (y_range[0] + y_range[1]) / 2
            else:
                y_center = None

            right_rows.append({
                "row_idx": row_idx,
                "y_center": y_center,
                "y_range": y_range,
                "data": row_data
            })

    # 左テーブルの各行のY範囲内にある右テーブルの行を紐付け
    for left_row in left_rows:
        if left_row["y_range"]:
            y1, y2 = left_row["y_range"]

            for right_row in right_rows:
                if right_row["y_center"] is not None:
                    # Y中心が左行のY範囲内にある場合、子として紐付け
                    if y1 <= right_row["y_center"] <= y2:
                        left_row["children"].append(right_row)

    # レコードを構築
    for left_row in left_rows:
        parent_data = left_row["data"]
        record = {
            "row_id": f"p{page_num}_t{table_idx}_r{left_row['row_idx']}",
            "parent_data": {
                "目": clean_value(parent_data[0]) if len(parent_data) > 0 else "",
                "本年度予算額": clean_value(parent_data[1]) if len(parent_data) > 1 else "",
                "前年度予算額": clean_value(parent_data[2]) if len(parent_data) > 2 else "",
                "比較": clean_value(parent_data[3]) if len(parent_data) > 3 else "",
            },
            "children": []
        }

        for child_row in left_row["children"]:
            child_data = child_row["data"]
            kubun = clean_value(child_data[0]) if len(child_data) > 0 else ""
            kingaku = clean_value(child_data[1]) if len(child_data) > 1 else ""
            setsumei = clean_value(child_data[2]) if len(child_data) > 2 else ""

            # 空行はスキップ
            if not kubun and not kingaku and not setsumei:
                continue

            record["children"].append({
                "区分": kubun,
                "金額": kingaku,
                "説明": setsumei,
            })

        records.append(record)

    # 左テーブルがない場合（右のみ）
    if not left_rows and right_rows:
        record = {
            "row_id": f"p{page_num}_t{table_idx}_orphan",
            "parent_data": {"目": "", "本年度予算額": "", "前年度予算額": "", "比較": ""},
            "children": []
        }
        for right_row in right_rows:
            child_data = right_row["data"]
            kubun = clean_value(child_data[0]) if len(child_data) > 0 else ""
            kingaku = clean_value(child_data[1]) if len(child_data) > 1 else ""
            setsumei = clean_value(child_data[2]) if len(child_data) > 2 else ""

            # 空行はスキップ
            if not kubun and not kingaku and not setsumei:
                continue

            record["children"].append({
                "区分": kubun,
                "金額": kingaku,
                "説明": setsumei,
            })
        if record["children"]:
            records.append(record)

    return records


def process_page(page_data: dict) -> dict:
    """1ページ分を処理"""
    tables = page_data.get("tables", [])
    page_num = page_data["page"]

    if not tables:
        return {"page": page_num, "records": []}

    left_tables, right_tables = classify_tables(tables)
    pairs = pair_tables_by_y(left_tables, right_tables)

    all_records = []

    for idx, (left, right) in enumerate(pairs):
        records = build_parent_child_structure_with_cells(left, right, page_num, idx)
        all_records.extend(records)

    return {"page": page_num, "records": all_records}


def process_all(input_path: str, output_path: str):
    """全ページを処理して出力"""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = {
        "source_file": data["source_file"],
        "pages": []
    }

    for page_data in data["pages"]:
        processed = process_page(page_data)
        result["pages"].append(processed)

    output_path = Path(output_path)

    if output_path.suffix == ".json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"JSON出力完了: {output_path}")

    elif output_path.suffix == ".xlsx":
        write_excel_denormalized(result, output_path)
        print(f"Excel出力完了: {output_path}")

    elif output_path.suffix == ".csv":
        write_csv_denormalized(result, output_path)
        print(f"CSV出力完了: {output_path}")

    else:
        print(f"未対応の出力形式: {output_path.suffix}")
        sys.exit(1)

    # サマリー
    total_records = sum(len(p["records"]) for p in result["pages"])
    total_children = sum(
        sum(len(r["children"]) for r in p["records"])
        for p in result["pages"]
    )
    print(f"  総ページ数: {len(result['pages'])}")
    print(f"  親レコード数: {total_records}")
    print(f"  子レコード数: {total_children}")


def write_csv_denormalized(data: dict, output_path: Path):
    """CSV出力（非正規化：全行に親情報を展開）"""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        # ヘッダー
        writer.writerow(["ページ", "目", "本年度予算額", "前年度予算額", "比較", "区分", "金額", "説明"])

        for page_data in data["pages"]:
            page_num = page_data["page"] + 1  # 1-indexed

            for record in page_data["records"]:
                parent = record["parent_data"]
                children = record["children"]

                if children:
                    for child in children:
                        writer.writerow([
                            page_num,
                            parent["目"],
                            parent["本年度予算額"],
                            parent["前年度予算額"],
                            parent["比較"],
                            child["区分"],
                            child["金額"],
                            child["説明"],
                        ])
                else:
                    writer.writerow([
                        page_num,
                        parent["目"],
                        parent["本年度予算額"],
                        parent["前年度予算額"],
                        parent["比較"],
                        "",
                        "",
                        "",
                    ])


def write_excel_denormalized(data: dict, output_path: Path):
    """Excel出力（非正規化）"""
    import xlsxwriter

    workbook = xlsxwriter.Workbook(str(output_path), {'nan_inf_to_errors': True})
    worksheet = workbook.add_worksheet("予算データ")

    # ヘッダー
    headers = ["ページ", "目", "本年度予算額", "前年度予算額", "比較", "区分", "金額", "説明"]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)

    row_num = 1
    for page_data in data["pages"]:
        page_num = page_data["page"] + 1

        for record in page_data["records"]:
            parent = record["parent_data"]
            children = record["children"]

            if children:
                for child in children:
                    worksheet.write(row_num, 0, page_num)
                    worksheet.write(row_num, 1, parent["目"])
                    worksheet.write(row_num, 2, parent["本年度予算額"])
                    worksheet.write(row_num, 3, parent["前年度予算額"])
                    worksheet.write(row_num, 4, parent["比較"])
                    worksheet.write(row_num, 5, child["区分"])
                    worksheet.write(row_num, 6, child["金額"])
                    worksheet.write(row_num, 7, child["説明"])
                    row_num += 1
            else:
                worksheet.write(row_num, 0, page_num)
                worksheet.write(row_num, 1, parent["目"])
                worksheet.write(row_num, 2, parent["本年度予算額"])
                worksheet.write(row_num, 3, parent["前年度予算額"])
                worksheet.write(row_num, 4, parent["比較"])
                row_num += 1

    workbook.close()


def main():
    if len(sys.argv) < 3:
        print("使用方法:")
        print("  python merge_tables_rdb_v2.py <input.json> <output.json|output.xlsx|output.csv>")
        print()
        print("例:")
        print("  python merge_tables_rdb_v2.py R8/output_cells.json R8/rdb_v2.csv")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not Path(input_path).exists():
        print(f"エラー: ファイルが見つかりません: {input_path}")
        sys.exit(1)

    process_all(input_path, output_path)


if __name__ == "__main__":
    main()

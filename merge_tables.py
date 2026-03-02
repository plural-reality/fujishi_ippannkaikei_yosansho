#!/usr/bin/env python3
"""
予算書テーブル結合スクリプト

img2tableで抽出した左右に分かれたテーブルを1つに結合する。
"""

import sys
import json
import csv
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Table:
    """テーブル情報"""
    bbox: dict
    rows: int
    cols: int
    data: list
    table_index: int


def classify_tables(tables: list[dict]) -> tuple[list[Table], list[Table]]:
    """
    テーブルをX座標で左右に分類
    - x1 < 1100 → 左側
    - x1 > 1200 → 右側
    """
    left_tables = []
    right_tables = []

    for t in tables:
        table = Table(
            bbox=t["bbox"],
            rows=t["rows"],
            cols=t["cols"],
            data=t["data"],
            table_index=t["table_index"]
        )

        if table.bbox["x1"] < 1100:
            left_tables.append(table)
        elif table.bbox["x1"] > 1200:
            right_tables.append(table)

    # Y座標でソート
    left_tables.sort(key=lambda t: t.bbox["y1"])
    right_tables.sort(key=lambda t: t.bbox["y1"])

    return left_tables, right_tables


def pair_tables(left_tables: list[Table], right_tables: list[Table], threshold: int = 300) -> list[tuple[Table | None, Table | None]]:
    """
    Y座標でテーブルをペアリング
    threshold: Y座標の差がこの値以内なら同一行とみなす
    """
    pairs = []
    used_right = set()

    for left in left_tables:
        best_match = None
        best_diff = float('inf')

        for i, right in enumerate(right_tables):
            if i in used_right:
                continue

            diff = abs(left.bbox["y1"] - right.bbox["y1"])
            if diff < threshold and diff < best_diff:
                best_diff = diff
                best_match = (i, right)

        if best_match:
            used_right.add(best_match[0])
            pairs.append((left, best_match[1]))
        else:
            pairs.append((left, None))

    # 未マッチの右テーブル
    for i, right in enumerate(right_tables):
        if i not in used_right:
            pairs.append((None, right))

    return pairs


def estimate_row_y_positions(table: Table) -> list[float]:
    """
    テーブルの各行のY座標を推定
    均等配分と仮定
    """
    if table.rows == 0:
        return []

    y1 = table.bbox["y1"]
    y2 = table.bbox["y2"]
    height = y2 - y1
    row_height = height / table.rows

    return [y1 + row_height * (i + 0.5) for i in range(table.rows)]


def merge_rows(left: Table | None, right: Table | None) -> list[list]:
    """
    左右テーブルの行を結合
    行数が異なる場合はY座標近似でマッチング
    """
    if left is None and right is None:
        return []

    if left is None:
        # 右のみ：左側を空で埋める
        return [[None] * 4 + row for row in right.data]

    if right is None:
        # 左のみ：右側を空で埋める
        return [row + [None] * 3 for row in left.data]

    # 両方ある場合
    left_rows = left.data
    right_rows = right.data

    if len(left_rows) == len(right_rows):
        # 行数一致：そのまま結合
        return [l + r for l, r in zip(left_rows, right_rows)]

    # 行数不一致：Y座標でマッチング
    left_y = estimate_row_y_positions(left)
    right_y = estimate_row_y_positions(right)

    merged = []
    used_right = set()

    for i, (left_row, ly) in enumerate(zip(left_rows, left_y)):
        best_match = None
        best_diff = float('inf')

        for j, ry in enumerate(right_y):
            if j in used_right:
                continue
            diff = abs(ly - ry)
            if diff < best_diff:
                best_diff = diff
                best_match = j

        if best_match is not None:
            used_right.add(best_match)
            merged.append(left_row + right_rows[best_match])
        else:
            merged.append(left_row + [None] * len(right_rows[0]) if right_rows else left_row)

    # 未マッチの右行
    for j, right_row in enumerate(right_rows):
        if j not in used_right:
            merged.append([None] * len(left_rows[0]) + right_row if left_rows else right_row)

    return merged


def merge_page_tables(page_data: dict) -> dict:
    """
    1ページ分のテーブルを結合
    """
    tables = page_data.get("tables", [])
    if not tables:
        return {"page": page_data["page"], "merged_tables": []}

    left_tables, right_tables = classify_tables(tables)
    pairs = pair_tables(left_tables, right_tables)

    merged_tables = []
    for left, right in pairs:
        merged_rows = merge_rows(left, right)
        if merged_rows:
            merged_tables.append({
                "rows": len(merged_rows),
                "cols": len(merged_rows[0]) if merged_rows else 0,
                "data": merged_rows,
                "left_bbox": left.bbox if left else None,
                "right_bbox": right.bbox if right else None,
            })

    return {
        "page": page_data["page"],
        "merged_tables": merged_tables
    }


def merge_all_tables(input_path: str, output_path: str):
    """
    全ページのテーブルを結合して出力
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = {
        "source_file": data["source_file"],
        "pages": []
    }

    for page_data in data["pages"]:
        merged_page = merge_page_tables(page_data)
        result["pages"].append(merged_page)

    output_path = Path(output_path)

    if output_path.suffix == ".json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"JSON出力完了: {output_path}")

    elif output_path.suffix == ".xlsx":
        write_excel(result, output_path)
        print(f"Excel出力完了: {output_path}")

    elif output_path.suffix == ".csv":
        write_csv(result, output_path)
        print(f"CSV出力完了: {output_path}")

    else:
        print(f"未対応の出力形式: {output_path.suffix}")
        sys.exit(1)

    # サマリー
    total_tables = sum(len(p["merged_tables"]) for p in result["pages"])
    print(f"  総ページ数: {len(result['pages'])}")
    print(f"  結合後のテーブル数: {total_tables}")


def write_excel(data: dict, output_path: Path):
    """Excel出力"""
    import xlsxwriter
    import math

    workbook = xlsxwriter.Workbook(str(output_path), {'nan_inf_to_errors': True})

    for page_data in data["pages"]:
        page_num = page_data["page"]
        tables = page_data["merged_tables"]

        if not tables:
            continue

        sheet_name = f"Page_{page_num + 1}"[:31]  # Excel sheet name limit
        worksheet = workbook.add_worksheet(sheet_name)

        row_offset = 0
        for table in tables:
            for i, row in enumerate(table["data"]):
                for j, cell in enumerate(row):
                    # NaN/None/inf を空文字に変換
                    if cell is None:
                        value = ""
                    elif isinstance(cell, float) and (math.isnan(cell) or math.isinf(cell)):
                        value = ""
                    else:
                        value = cell
                    worksheet.write(row_offset + i, j, value)
            row_offset += len(table["data"]) + 1  # 1行空ける

    workbook.close()


def write_csv(data: dict, output_path: Path):
    """CSV出力（全ページを1ファイルに）"""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        for page_data in data["pages"]:
            page_num = page_data["page"]
            tables = page_data["merged_tables"]

            if not tables:
                continue

            writer.writerow([f"=== Page {page_num + 1} ==="])

            for table in tables:
                for row in table["data"]:
                    cleaned_row = [cell if cell is not None else "" for cell in row]
                    writer.writerow(cleaned_row)
                writer.writerow([])  # 空行


def main():
    if len(sys.argv) < 3:
        print("使用方法:")
        print("  python merge_tables.py <input.json> <output.json|output.xlsx|output.csv>")
        print()
        print("例:")
        print("  python merge_tables.py R8/output_bugget.json R8/merged.json")
        print("  python merge_tables.py R8/output_bugget.json R8/merged.xlsx")
        print("  python merge_tables.py R8/output_bugget.json R8/merged.csv")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not Path(input_path).exists():
        print(f"エラー: ファイルが見つかりません: {input_path}")
        sys.exit(1)

    merge_all_tables(input_path, output_path)


if __name__ == "__main__":
    main()

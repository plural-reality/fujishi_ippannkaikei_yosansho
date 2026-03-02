#!/usr/bin/env python3
"""
予算書テーブル結合スクリプト（RDB構造対応版）

左テーブル（親）と右テーブル（子）を1対多の関係で紐付け。
CSV出力時は非正規化して全行に親情報を展開。
"""

import sys
import json
import csv
import math
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Table:
    """テーブル情報"""
    bbox: dict
    rows: int
    cols: int
    data: list
    table_index: int


@dataclass
class ParentRow:
    """親テーブルの行"""
    row_id: str
    y_start: float
    y_end: float
    data: list  # [目, 本年度予算額, 前年度予算額, 比較]
    children: list = field(default_factory=list)  # ChildRowのリスト


@dataclass
class ChildRow:
    """子テーブルの行"""
    parent_id: str | None
    y_center: float
    data: list  # [区分, 金額, 説明]


def clean_value(val):
    """NaN/None/infを空文字に変換"""
    if val is None:
        return ""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return ""
    return val


def classify_tables(tables: list[dict]) -> tuple[list[Table], list[Table]]:
    """テーブルをX座標で左右に分類"""
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

    left_tables.sort(key=lambda t: t.bbox["y1"])
    right_tables.sort(key=lambda t: t.bbox["y1"])

    return left_tables, right_tables


def pair_tables_by_y(left_tables: list[Table], right_tables: list[Table], threshold: int = 300):
    """Y座標でテーブルをペアリング"""
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

    for i, right in enumerate(right_tables):
        if i not in used_right:
            pairs.append((None, right))

    return pairs


def estimate_row_y_ranges(table: Table) -> list[tuple[float, float]]:
    """テーブルの各行のY範囲を推定"""
    if table.rows == 0:
        return []

    y1 = table.bbox["y1"]
    y2 = table.bbox["y2"]
    height = y2 - y1
    row_height = height / table.rows

    return [(y1 + row_height * i, y1 + row_height * (i + 1)) for i in range(table.rows)]


def estimate_row_y_centers(table: Table) -> list[float]:
    """テーブルの各行のY中心座標を推定"""
    if table.rows == 0:
        return []

    y1 = table.bbox["y1"]
    y2 = table.bbox["y2"]
    height = y2 - y1
    row_height = height / table.rows

    return [y1 + row_height * (i + 0.5) for i in range(table.rows)]


def build_parent_child_structure(left: Table | None, right: Table | None, page_num: int, table_idx: int) -> list[ParentRow]:
    """
    左右テーブルから親子構造を構築
    左の各行のY範囲内にある右の行を子として紐付け
    """
    if left is None and right is None:
        return []

    # 親行（左テーブル）を作成
    parents = []
    if left is not None:
        left_y_ranges = estimate_row_y_ranges(left)
        for i, (row_data, (y_start, y_end)) in enumerate(zip(left.data, left_y_ranges)):
            # ヘッダー行（最初の数行）はスキップするかどうか判断
            row_id = f"p{page_num}_t{table_idx}_r{i}"
            parent = ParentRow(
                row_id=row_id,
                y_start=y_start,
                y_end=y_end,
                data=row_data,
                children=[]
            )
            parents.append(parent)

    # 子行（右テーブル）を親に紐付け
    if right is not None:
        right_y_centers = estimate_row_y_centers(right)

        for row_data, y_center in zip(right.data, right_y_centers):
            child = ChildRow(
                parent_id=None,
                y_center=y_center,
                data=row_data
            )

            # Y座標が範囲内の親を探す
            matched = False
            for parent in parents:
                if parent.y_start <= y_center <= parent.y_end:
                    child.parent_id = parent.row_id
                    parent.children.append(child)
                    matched = True
                    break

            # マッチしなかった場合、最も近い親に紐付け
            if not matched and parents:
                closest_parent = min(parents, key=lambda p: min(abs(p.y_start - y_center), abs(p.y_end - y_center)))
                child.parent_id = closest_parent.row_id
                closest_parent.children.append(child)

    # 左テーブルがない場合（右のみ）
    if left is None and right is not None:
        # 仮の親を作成
        parent = ParentRow(
            row_id=f"p{page_num}_t{table_idx}_orphan",
            y_start=right.bbox["y1"],
            y_end=right.bbox["y2"],
            data=[None, None, None, None],
            children=[]
        )
        right_y_centers = estimate_row_y_centers(right)
        for row_data, y_center in zip(right.data, right_y_centers):
            child = ChildRow(parent_id=parent.row_id, y_center=y_center, data=row_data)
            parent.children.append(child)
        parents.append(parent)

    return parents


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
        parents = build_parent_child_structure(left, right, page_num, idx)

        for parent in parents:
            record = {
                "row_id": parent.row_id,
                "parent_data": {
                    "目": clean_value(parent.data[0]) if len(parent.data) > 0 else "",
                    "本年度予算額": clean_value(parent.data[1]) if len(parent.data) > 1 else "",
                    "前年度予算額": clean_value(parent.data[2]) if len(parent.data) > 2 else "",
                    "比較": clean_value(parent.data[3]) if len(parent.data) > 3 else "",
                },
                "children": []
            }

            for child in parent.children:
                child_record = {
                    "区分": clean_value(child.data[0]) if len(child.data) > 0 else "",
                    "金額": clean_value(child.data[1]) if len(child.data) > 1 else "",
                    "説明": clean_value(child.data[2]) if len(child.data) > 2 else "",
                }
                record["children"].append(child_record)

            all_records.append(record)

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
                    # 子があれば子の数だけ行を出力
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
                    # 子がなければ親のみ出力
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
        print("  python merge_tables_rdb.py <input.json> <output.json|output.xlsx|output.csv>")
        print()
        print("例:")
        print("  python merge_tables_rdb.py R8/output_bugget.json R8/rdb.json")
        print("  python merge_tables_rdb.py R8/output_bugget.json R8/rdb.xlsx")
        print("  python merge_tables_rdb.py R8/output_bugget.json R8/rdb.csv")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not Path(input_path).exists():
        print(f"エラー: ファイルが見つかりません: {input_path}")
        sys.exit(1)

    process_all(input_path, output_path)


if __name__ == "__main__":
    main()

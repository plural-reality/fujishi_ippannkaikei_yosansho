#!/usr/bin/env python3
"""
img2table を使用したPDF表構造抽出スクリプト

OpenCVベースで罫線からセル構造を検出し、Tesseractで日本語OCRを実行。
LLMによる構造推測が不要になり、精度が向上する。
"""

import sys
import json
from pathlib import Path
from img2table.document import PDF
from img2table.ocr import TesseractOCR


def extract_tables(pdf_path: str, output_path: str, pages: list[int] | None = None):
    """
    PDFから表を抽出してJSONまたはExcelに出力

    Args:
        pdf_path: 入力PDFファイルのパス
        output_path: 出力ファイルのパス (.json または .xlsx)
        pages: 処理するページ番号のリスト (0-indexed)。Noneの場合は全ページ
    """
    # Tesseract OCR (日本語)
    ocr = TesseractOCR(lang="jpn")

    # PDF読み込み
    pdf = PDF(src=pdf_path, pages=pages)

    # 表抽出
    # implicit_rows=True: 罫線がない行も検出を試みる
    # borderless_tables=True: 罫線のない表も検出を試みる
    extracted_tables = pdf.extract_tables(
        ocr=ocr,
        implicit_rows=True,
        borderless_tables=False,  # 予算書は罫線があるのでFalse
        min_confidence=50,
    )

    output_path = Path(output_path)

    if output_path.suffix == ".xlsx":
        # Excel出力
        pdf.to_xlsx(
            dest=str(output_path),
            ocr=ocr,
            implicit_rows=True,
            borderless_tables=False,
            min_confidence=50,
        )
        print(f"Excel出力完了: {output_path}")
        return

    # JSON出力
    result = {
        "source_file": str(pdf_path),
        "pages": []
    }

    for page_num, tables in extracted_tables.items():
        page_data = {
            "page": page_num,
            "tables": []
        }

        for table_idx, table in enumerate(tables):
            # DataFrameに変換
            df = table.df

            # セルレベルのbbox情報を抽出
            cells_data = []
            if hasattr(table, 'content') and table.content:
                for row_idx, row_cells in table.content.items():
                    row_data = []
                    for col_idx, cell in enumerate(row_cells):
                        if cell is not None:
                            cell_info = {
                                "value": cell.value,
                                "bbox": {
                                    "x1": int(cell.bbox.x1),
                                    "y1": int(cell.bbox.y1),
                                    "x2": int(cell.bbox.x2),
                                    "y2": int(cell.bbox.y2),
                                }
                            }
                        else:
                            cell_info = {"value": None, "bbox": None}
                        row_data.append(cell_info)
                    cells_data.append(row_data)

            table_data = {
                "table_index": table_idx,
                "bbox": {
                    "x1": int(table.bbox.x1),
                    "y1": int(table.bbox.y1),
                    "x2": int(table.bbox.x2),
                    "y2": int(table.bbox.y2),
                },
                "rows": len(df),
                "cols": len(df.columns),
                "data": df.values.tolist(),
                "cells": cells_data,  # セルレベルのbbox情報
                "columns": [str(c) for c in df.columns.tolist()] if not df.empty else [],
            }
            page_data["tables"].append(table_data)

        result["pages"].append(page_data)

    # JSON書き出し
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"JSON出力完了: {output_path}")

    # サマリー
    total_tables = sum(len(tables) for tables in extracted_tables.values())
    print(f"  総ページ数: {len(extracted_tables)}")
    print(f"  検出された表の総数: {total_tables}")


def main():
    if len(sys.argv) < 3:
        print("使用方法:")
        print("  python extract_img2table.py <input.pdf> <output.json|output.xlsx> [pages]")
        print()
        print("例:")
        print("  python extract_img2table.py budget.pdf output.json")
        print("  python extract_img2table.py budget.pdf output.xlsx")
        print("  python extract_img2table.py budget.pdf output.json 0,1,2  # 最初の3ページのみ")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2]

    # ページ指定 (オプション)
    pages = None
    if len(sys.argv) >= 4:
        pages = [int(p.strip()) for p in sys.argv[3].split(",")]

    if not Path(pdf_path).exists():
        print(f"エラー: ファイルが見つかりません: {pdf_path}")
        sys.exit(1)

    extract_tables(pdf_path, output_path, pages)


if __name__ == "__main__":
    main()

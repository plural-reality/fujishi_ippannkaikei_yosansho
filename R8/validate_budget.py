#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
予算データ検証スクリプト
JSONとCSVの整合性、数値の妥当性をチェック

使い方:
  python validate_budget.py                    # R8/json/ をチェック
  python validate_budget.py path/to/json_dir   # 指定ディレクトリをチェック
"""

import json
import csv
import sys
import re
from pathlib import Path
from collections import defaultdict


class BudgetValidator:
    def __init__(self, json_dir: Path):
        self.json_dir = json_dir
        self.errors = []
        self.warnings = []
        self.stats = defaultdict(int)

    def error(self, msg: str):
        self.errors.append(f"[ERROR] {msg}")
        self.stats["errors"] += 1

    def warn(self, msg: str):
        self.warnings.append(f"[WARN] {msg}")
        self.stats["warnings"] += 1

    def info(self, msg: str):
        print(f"[INFO] {msg}")

    # ========== 1. JSON構文チェック ==========
    def check_json_syntax(self) -> dict:
        """全JSONファイルの構文チェック"""
        self.info("=== JSON構文チェック ===")
        json_files = list(self.json_dir.glob("*.json"))
        valid_data = {}

        for f in json_files:
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                valid_data[f.name] = data
                self.stats["valid_json"] += 1
            except json.JSONDecodeError as e:
                self.error(f"{f.name}: JSON構文エラー - {e}")

        self.info(f"  有効なJSON: {self.stats['valid_json']}/{len(json_files)}")
        return valid_data

    # ========== 2. 構造チェック ==========
    def check_structure(self, data: dict, filename: str):
        """JSON構造の妥当性チェック"""
        if filename == "_merged.json":
            return self._check_merged_structure(data)

        # 個別款ファイルの構造チェック
        if "歳入" not in data and "歳出" not in data:
            self.error(f"{filename}: '歳入' または '歳出' キーが存在しない")
            return

        for section_key in ["歳入", "歳出"]:
            section = data.get(section_key)
            if not section:
                continue

            if "款" not in section:
                self.error(f"{filename}: '{section_key}' に '款' がない")
                continue

            for kan_obj in section["款"]:
                self._check_kan_structure(kan_obj, filename)

    def _check_merged_structure(self, data: dict):
        """_merged.json の構造チェック"""
        for section_key in ["歳入", "歳出"]:
            if section_key not in data:
                self.error(f"_merged.json: '{section_key}' セクションがない")
                continue

            section = data[section_key]
            if "款" not in section:
                self.error(f"_merged.json: '{section_key}' に '款' がない")
                continue

            self.info(f"  {section_key}: {len(section['款'])}款")

    def _check_kan_structure(self, kan_obj: dict, filename: str):
        """款の構造チェック"""
        if not kan_obj:
            self.error(f"{filename}: 空の款オブジェクト")
            return

        kan_name = next(iter(kan_obj.keys()))
        kan_data = kan_obj[kan_name]

        # 必須フィールドチェック
        if "本年度予算額" not in kan_data:
            self.warn(f"{filename}: 款「{kan_name}」に本年度予算額がない")

        if "項" not in kan_data:
            self.warn(f"{filename}: 款「{kan_name}」に項がない")

    # ========== 3. 数値整合性チェック ==========
    def check_numeric_consistency(self, data: dict, filename: str):
        """階層間の数値整合性チェック"""
        if filename == "_merged.json":
            return self._check_merged_totals(data)

        for section_key in ["歳入", "歳出"]:
            section = data.get(section_key)
            if not section:
                continue

            for kan_obj in section.get("款", []):
                self._check_kan_totals(kan_obj, filename, section_key)

    def _check_merged_totals(self, data: dict):
        """歳入・歳出の合計チェック"""
        totals = {}

        for section_key in ["歳入", "歳出"]:
            section = data.get(section_key, {})
            total = 0
            for kan_obj in section.get("款", []):
                kan_name = next(iter(kan_obj.keys()))
                kan_data = kan_obj[kan_name]
                amount = kan_data.get("本年度予算額", 0)
                if isinstance(amount, (int, float)):
                    total += amount
            totals[section_key] = total
            self.info(f"  {section_key}合計: {total:,}千円")

        if "歳入" in totals and "歳出" in totals:
            diff = totals["歳入"] - totals["歳出"]
            if diff != 0:
                self.warn(f"歳入と歳出の差額: {diff:,}千円（通常は一致）")

    def _check_kan_totals(self, kan_obj: dict, filename: str, section: str):
        """款内の項合計チェック"""
        kan_name = next(iter(kan_obj.keys()))
        kan_data = kan_obj[kan_name]
        kan_amount = kan_data.get("本年度予算額", 0)

        # 項の合計を計算
        kou_total = 0
        for kou_obj in kan_data.get("項", []):
            kou_name = next(iter(kou_obj.keys()))
            kou_data = kou_obj[kou_name]
            kou_amount = kou_data.get("本年度予算額", 0)
            if isinstance(kou_amount, (int, float)):
                kou_total += kou_amount

            # 目の合計チェック
            self._check_kou_totals(kou_obj, filename, section, kan_name)

        # 項合計と款金額の比較
        if isinstance(kan_amount, (int, float)) and kou_total > 0:
            if kan_amount != kou_total:
                diff = kan_amount - kou_total
                self.error(f"{filename}: {section}「{kan_name}」項合計不一致 "
                          f"(款額={kan_amount:,}, 項計={kou_total:,}, 差={diff:,})")

    def _check_kou_totals(self, kou_obj: dict, filename: str, section: str, kan_name: str):
        """項内の目合計チェック"""
        kou_name = next(iter(kou_obj.keys()))
        kou_data = kou_obj[kou_name]
        kou_amount = kou_data.get("本年度予算額", 0)

        moku_total = 0
        for moku_obj in kou_data.get("目", []):
            moku_name = next(iter(moku_obj.keys()))
            moku_data = moku_obj[moku_name]
            moku_amount = moku_data.get("本年度予算額", 0)
            if isinstance(moku_amount, (int, float)):
                moku_total += moku_amount

        if isinstance(kou_amount, (int, float)) and moku_total > 0:
            if kou_amount != moku_total:
                diff = kou_amount - moku_total
                self.warn(f"{filename}: {section}「{kan_name}→{kou_name}」目合計不一致 "
                         f"(項額={kou_amount:,}, 目計={moku_total:,}, 差={diff:,})")

    # ========== 4. 計算式検証 ==========
    def check_formulas(self, data: dict, filename: str):
        """計算式の妥当性チェック"""
        self._traverse_for_formulas(data, filename, [])

    def _traverse_for_formulas(self, obj, filename: str, path: list):
        """再帰的に計算式を探して検証"""
        if isinstance(obj, dict):
            # 計算式フィールドを探す
            formula_keys = ["調定見込額", "算定標準額", "測定見込額"]
            amount = obj.get("金額")

            for key in formula_keys:
                if key in obj and isinstance(obj[key], str):
                    formula = obj[key]
                    self._validate_formula(formula, amount, filename, path + [key])

            # 再帰
            for k, v in obj.items():
                self._traverse_for_formulas(v, filename, path + [k])

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._traverse_for_formulas(item, filename, path + [f"[{i}]"])

    def _validate_formula(self, formula: str, expected_amount, filename: str, path: list):
        """計算式を評価して金額と比較"""
        try:
            # %を/100に変換
            expr = formula.replace("%", "/100")
            # *を掛け算として評価
            result = eval(expr)

            if expected_amount is not None and isinstance(expected_amount, (int, float)):
                # 誤差10%以内なら許容
                if expected_amount > 0:
                    error_rate = abs(result - expected_amount) / expected_amount
                    if error_rate > 0.1:
                        location = " → ".join(str(p) for p in path)
                        self.warn(f"{filename}: 計算式不整合 [{location}] "
                                 f"式={formula} 結果={result:.0f} 金額={expected_amount}")
        except Exception:
            pass  # 評価できない式は無視

    # ========== 5. CSVとの整合性チェック ==========
    def check_csv_consistency(self, merged_data: dict, csv_path: Path):
        """CSVとJSONの整合性チェック"""
        self.info("=== CSV整合性チェック ===")

        if not csv_path.exists():
            self.error(f"CSVファイルが見つからない: {csv_path}")
            return

        # CSVから款ごとの金額を抽出
        csv_kans = self._parse_csv_kans(csv_path)

        # JSONの款金額と比較
        for section_key in ["歳入", "歳出"]:
            section = merged_data.get(section_key, {})
            for kan_obj in section.get("款", []):
                kan_name = next(iter(kan_obj.keys()))
                kan_data = kan_obj[kan_name]
                json_amount = kan_data.get("本年度予算額", 0)

                if kan_name in csv_kans:
                    csv_amount = csv_kans[kan_name]
                    if json_amount != csv_amount:
                        self.error(f"款「{kan_name}」金額不一致: "
                                  f"JSON={json_amount:,} CSV={csv_amount:,}")
                else:
                    self.warn(f"款「{kan_name}」がCSVに見つからない")

    def _parse_csv_kans(self, csv_path: Path) -> dict:
        """CSVから款レベルの金額を抽出"""
        kans = {}
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 款列に値があり、項列が空 = 款行
                if row.get("款") and not row.get("項"):
                    kan_name = row["款"]
                    r7 = row.get("R7", "")
                    if r7:
                        try:
                            kans[kan_name] = int(r7)
                        except ValueError:
                            pass
        return kans

    # ========== メイン実行 ==========
    def run(self, csv_path: Path = None):
        """全チェックを実行"""
        print("=" * 60)
        print("予算データ検証")
        print("=" * 60)

        # 1. JSON構文チェック
        valid_data = self.check_json_syntax()

        if not valid_data:
            print("\n有効なJSONがありません")
            return False

        # 2-4. 各ファイルの検証
        self.info("=== 構造・数値・計算式チェック ===")
        for filename, data in valid_data.items():
            self.check_structure(data, filename)
            self.check_numeric_consistency(data, filename)
            self.check_formulas(data, filename)

        # 5. CSV整合性チェック
        if csv_path and "_merged.json" in valid_data:
            self.check_csv_consistency(valid_data["_merged.json"], csv_path)

        # 結果サマリー
        print("\n" + "=" * 60)
        print("検証結果サマリー")
        print("=" * 60)
        print(f"  チェックしたJSON: {len(valid_data)}ファイル")
        print(f"  エラー: {len(self.errors)}")
        print(f"  警告: {len(self.warnings)}")

        if self.errors:
            print("\n--- エラー ---")
            for e in self.errors[:20]:  # 最大20件
                print(e)
            if len(self.errors) > 20:
                print(f"  ... 他 {len(self.errors) - 20} 件")

        if self.warnings:
            print("\n--- 警告 ---")
            for w in self.warnings[:20]:
                print(w)
            if len(self.warnings) > 20:
                print(f"  ... 他 {len(self.warnings) - 20} 件")

        return len(self.errors) == 0


def main():
    # デフォルトパス
    script_dir = Path(__file__).parent
    json_dir = script_dir / "json"
    csv_path = script_dir / "8年度予算.csv"

    # コマンドライン引数
    if len(sys.argv) >= 2:
        json_dir = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        csv_path = Path(sys.argv[2])

    if not json_dir.exists():
        print(f"エラー: ディレクトリが見つからない: {json_dir}")
        sys.exit(1)

    validator = BudgetValidator(json_dir)
    success = validator.run(csv_path)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

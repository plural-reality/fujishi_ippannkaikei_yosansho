#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
富士市予算書 JSON バリデーション

README.md のルールに忠実に従い、JSON構造を検証する。

対応形式:
1. 個別款ファイル: {"款名": {本年度予算額, 前年度予算額, 項: [...]}}
2. 統合ファイル: {"歳入": {"款": [...]}, "歳出": {"款": [...]}}
3. 部分統合: {"款": [...]}
4. マージ済みファイル: {"歳入": {"款": [...]}, "歳出": {"款": [...]}} (R6/R7/R8形式)

ルール:
1. 各レベル（款/項/目/節）は {名称: データ} 形式（単一キー）
2. 金額は整数（千円単位）
3. 説明の子項目は {名前: {金額: int, ...}} 形式
4. 計算式は "数値*数値%" のようなテキスト形式
5. 各階層の合計値は子階層の合計と一致すること

使い方:
    python validate_json.py <json_file> [json_file2 ...]
    python validate_json.py R8/json/*.json
    python validate_json.py merged_budget.json --check-sums
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple, Any


class ValidationError:
    """検証エラーを表すクラス"""
    def __init__(self, path: str, message: str, severity: str = "error"):
        self.path = path
        self.message = message
        self.severity = severity  # "error" or "warning"

    def __str__(self):
        marker = "ERROR" if self.severity == "error" else "WARN"
        return f"[{marker}] {self.path}: {self.message}"


class BudgetJsonValidator:
    """予算JSONのバリデータ"""

    def __init__(self, check_sums: bool = False):
        self.errors: List[ValidationError] = []
        self.check_sums = check_sums  # 階層間合計値チェックを行うか
        self.sum_mismatches: List[dict] = []  # 合計不一致の詳細
        self.negative_values: List[dict] = []  # 負の値
        self.null_issues: List[dict] = []  # Null値の問題

    def error(self, path: str, message: str):
        self.errors.append(ValidationError(path, message, "error"))

    def warn(self, path: str, message: str):
        self.errors.append(ValidationError(path, message, "warning"))

    def validate_file(self, filepath: str) -> Tuple[bool, List[ValidationError]]:
        """JSONファイルを検証"""
        self.errors = []
        path = Path(filepath)

        # ファイル読み込み
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.error(filepath, "ファイルが見つからない")
            return False, self.errors
        except json.JSONDecodeError as e:
            self.error(filepath, f"JSON構文エラー: {e}")
            return False, self.errors

        # ファイル形式を自動検出して検証
        self._validate_root(data, path.name)

        error_count = sum(1 for e in self.errors if e.severity == "error")
        return error_count == 0, self.errors

    def _validate_root(self, data: dict, filename: str):
        """ルートレベルを検証（形式を自動検出）"""
        if not isinstance(data, dict):
            self.error(filename, f"ルートは辞書である必要がある（実際: {type(data).__name__}）")
            return

        keys = set(data.keys())

        # 形式1: 統合ファイル {"歳入": {...}, "歳出": {...}}
        if keys & {"歳入", "歳出"}:
            self._validate_merged(data, filename)

        # 形式2: 部分統合 {"款": [...]}
        elif keys == {"款"}:
            self._validate_kan_list(data["款"], filename)

        # 形式3: 個別款ファイル {"款名": {...}}
        elif len(keys) == 1:
            self._validate_kan_content(data, filename)

        else:
            self.error(filename, f"不明な形式: keys={list(keys)}")

    def _validate_merged(self, data: dict, filename: str):
        """統合ファイル形式を検証"""
        for section_key in ["歳入", "歳出"]:
            if section_key not in data:
                continue

            section = data[section_key]
            section_path = f"{filename}/{section_key}"

            if not isinstance(section, dict):
                self.error(section_path, "セクションは辞書である必要がある")
                continue

            if "款" not in section:
                self.error(section_path, "'款' が必須だが存在しない")
                continue

            self._validate_kan_list(section["款"], section_path)

    def _validate_kan_list(self, kan_list: Any, path: str):
        """款の配列を検証"""
        if not isinstance(kan_list, list):
            self.error(path, "'款' は配列である必要がある")
            return

        if len(kan_list) == 0:
            self.error(path, "'款' が空の配列")
            return

        for i, kan_obj in enumerate(kan_list):
            self._validate_kan_content(kan_obj, f"{path}/款[{i}]")

    def _validate_kan_content(self, data: dict, path: str):
        """款の中身を検証（個別款ファイルのルート）"""
        valid, name, kan_data = self._validate_single_key_dict(data, path, "款")
        if not valid:
            return

        kan_path = f"{path}/{name}"

        # 本年度予算額・前年度予算額は必須
        self._validate_amount(kan_data, "本年度予算額", kan_path, required=True)
        self._validate_amount(kan_data, "前年度予算額", kan_path, required=True)

        # 項は必須
        if "項" not in kan_data:
            self.error(kan_path, "'項' が必須だが存在しない")
        elif not isinstance(kan_data["項"], list):
            self.error(kan_path, "'項' は配列である必要がある")
        elif len(kan_data["項"]) == 0:
            self.error(kan_path, "'項' が空の配列")
        else:
            for i, kou in enumerate(kan_data["項"]):
                self._validate_kou(kou, f"{kan_path}/項[{i}]")

    def _validate_single_key_dict(self, obj: Any, path: str, level: str) -> Tuple[bool, str, dict]:
        """
        単一キーの辞書であることを検証
        Returns: (is_valid, name, data)
        """
        if not isinstance(obj, dict):
            self.error(path, f"{level}は辞書である必要がある（実際: {type(obj).__name__}）")
            return False, "", {}

        if len(obj) == 0:
            self.error(path, f"{level}が空")
            return False, "", {}

        if len(obj) != 1:
            keys = list(obj.keys())
            self.error(path, f"{level}は単一キーである必要がある（実際: {keys}）")
            return False, "", {}

        name = list(obj.keys())[0]
        data = obj[name]

        if not isinstance(name, str):
            self.error(path, f"{level}の名称は文字列である必要がある")
            return False, "", {}

        if not isinstance(data, dict):
            self.error(path, f"{level}「{name}」のデータは辞書である必要がある")
            return False, name, {}

        return True, name, data

    def _validate_amount(self, data: dict, field: str, path: str, required: bool = True) -> bool:
        """金額フィールドを検証"""
        if field not in data:
            if required:
                self.error(path, f"'{field}' が必須だが存在しない")
                return False
            return True

        value = data[field]

        # null は許容（前年度予算額が存在しない場合など）
        if value is None:
            return True

        if not isinstance(value, int):
            self.error(path, f"'{field}' は整数である必要がある（実際: {type(value).__name__}, 値: {value}）")
            return False

        return True

    def _validate_formula(self, value: str, path: str):
        """計算式の形式を検証（警告のみ）"""
        if not isinstance(value, str):
            return

        # 計算式っぽい文字列かチェック
        if '*' in value or '×' in value or '/' in value or '÷' in value:
            normalized = value.replace(',', '').replace(' ', '').replace('　', '')
            if not re.match(r'^[\d.]+[*×/÷][\d.]+%?$', normalized):
                self.warn(path, f"計算式の形式が不正: '{value}'（推奨: '408000*98.9%'）")

    def _validate_setsumei(self, setsumei: Any, path: str):
        """説明フィールドを検証"""
        if not isinstance(setsumei, dict):
            self.error(path, f"説明は辞書である必要がある（実際: {type(setsumei).__name__}）")
            return

        for key, value in setsumei.items():
            item_path = f"{path}/{key}"

            if isinstance(value, dict):
                # 子項目: {名前: {金額: int, ...}}
                if "金額" in value:
                    self._validate_amount(value, "金額", item_path, required=True)

                # 計算式フィールドをチェック
                for formula_key in ["調定見込額", "算定標準額", "測定見込額"]:
                    if formula_key in value:
                        self._validate_formula(value[formula_key], f"{item_path}/{formula_key}")

                # ネストした説明（内訳など）
                if "内訳" in value and isinstance(value["内訳"], dict):
                    self._validate_setsumei(value["内訳"], f"{item_path}/内訳")

            elif isinstance(value, str):
                self._validate_formula(value, item_path)

            elif isinstance(value, (int, type(None))):
                pass  # OK

            else:
                self.warn(item_path, f"説明の値の型が想定外: {type(value).__name__}")

    def _validate_setsu(self, setsu: dict, path: str):
        """節を検証"""
        valid, name, data = self._validate_single_key_dict(setsu, path, "節")
        if not valid:
            return

        setsu_path = f"{path}/{name}"

        # 金額は必須
        self._validate_amount(data, "金額", setsu_path, required=True)

        # 説明（オプション）
        if "説明" in data:
            self._validate_setsumei(data["説明"], f"{setsu_path}/説明")

    def _validate_moku(self, moku: dict, path: str):
        """目を検証"""
        valid, name, data = self._validate_single_key_dict(moku, path, "目")
        if not valid:
            return

        moku_path = f"{path}/{name}"

        # 本年度予算額・前年度予算額は必須
        self._validate_amount(data, "本年度予算額", moku_path, required=True)
        self._validate_amount(data, "前年度予算額", moku_path, required=True)

        # 節（オプション - 歳入など節がない場合もある）
        if "節" in data:
            if not isinstance(data["節"], list):
                self.error(moku_path, "'節' は配列である必要がある")
            else:
                for i, setsu in enumerate(data["節"]):
                    self._validate_setsu(setsu, f"{moku_path}/節[{i}]")

    def _validate_kou(self, kou: dict, path: str):
        """項を検証"""
        valid, name, data = self._validate_single_key_dict(kou, path, "項")
        if not valid:
            return

        kou_path = f"{path}/{name}"

        # 本年度予算額・前年度予算額は必須
        self._validate_amount(data, "本年度予算額", kou_path, required=True)
        self._validate_amount(data, "前年度予算額", kou_path, required=True)

        # 目は必須
        if "目" not in data:
            self.error(kou_path, "'目' が必須だが存在しない")
        elif not isinstance(data["目"], list):
            self.error(kou_path, "'目' は配列である必要がある")
        elif len(data["目"]) == 0:
            self.error(kou_path, "'目' が空の配列")
        else:
            for i, moku in enumerate(data["目"]):
                self._validate_moku(moku, f"{kou_path}/目[{i}]")

    # ========================================
    # マージ済みJSON (R6/R7/R8形式) の合計値チェック
    # ========================================

    def validate_merged_sums(self, filepath: str) -> Tuple[bool, List[dict]]:
        """
        マージ済みJSONの階層間合計値を検証
        各階層で親のR8が子の合計と一致するかチェック

        Returns: (is_valid, mismatches)
        """
        self.sum_mismatches = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.error(filepath, f"ファイル読み込みエラー: {e}")
            return False, []

        # R6/R7/R8 すべてチェック
        for year_key in ["R6", "R7", "R8"]:
            for section_key in ["歳入", "歳出"]:
                if section_key in data and "款" in data[section_key]:
                    self._check_kan_sums(
                        data[section_key]["款"],
                        f"{section_key}",
                        year_key
                    )

        return len(self.sum_mismatches) == 0, self.sum_mismatches

    def _get_amount(self, data: dict, year_key: str) -> int:
        """指定された年度の金額を取得（nullは0として扱う）"""
        value = data.get(year_key)
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        return 0

    def _check_kan_sums(self, kan_list: list, path: str, year_key: str):
        """款レベルの合計チェック: 款のR8 == 子の項のR8の合計"""
        for i, kan_obj in enumerate(kan_list):
            if not isinstance(kan_obj, dict) or len(kan_obj) != 1:
                continue

            kan_name = list(kan_obj.keys())[0]
            kan_data = kan_obj[kan_name]
            kan_path = f"{path}/款[{i}]/{kan_name}"

            if not isinstance(kan_data, dict):
                continue

            parent_amount = self._get_amount(kan_data, year_key)

            # 項の合計を計算
            if "項" in kan_data and isinstance(kan_data["項"], list):
                children_sum = 0
                for kou_obj in kan_data["項"]:
                    if isinstance(kou_obj, dict) and len(kou_obj) == 1:
                        kou_name = list(kou_obj.keys())[0]
                        kou_data = kou_obj[kou_name]
                        if isinstance(kou_data, dict):
                            children_sum += self._get_amount(kou_data, year_key)

                if parent_amount != children_sum and parent_amount != 0:
                    diff = parent_amount - children_sum
                    self.sum_mismatches.append({
                        "path": kan_path,
                        "year": year_key,
                        "level": "款→項",
                        "parent_value": parent_amount,
                        "children_sum": children_sum,
                        "difference": diff
                    })

                # 項の中の目もチェック
                self._check_kou_sums(kan_data["項"], kan_path, year_key)

    def _check_kou_sums(self, kou_list: list, path: str, year_key: str):
        """項レベルの合計チェック: 項のR8 == 子の目のR8の合計"""
        for i, kou_obj in enumerate(kou_list):
            if not isinstance(kou_obj, dict) or len(kou_obj) != 1:
                continue

            kou_name = list(kou_obj.keys())[0]
            kou_data = kou_obj[kou_name]
            kou_path = f"{path}/項[{i}]/{kou_name}"

            if not isinstance(kou_data, dict):
                continue

            parent_amount = self._get_amount(kou_data, year_key)

            # 目の合計を計算
            if "目" in kou_data and isinstance(kou_data["目"], list):
                children_sum = 0
                for moku_obj in kou_data["目"]:
                    if isinstance(moku_obj, dict) and len(moku_obj) == 1:
                        moku_name = list(moku_obj.keys())[0]
                        moku_data = moku_obj[moku_name]
                        if isinstance(moku_data, dict):
                            children_sum += self._get_amount(moku_data, year_key)

                if parent_amount != children_sum and parent_amount != 0:
                    diff = parent_amount - children_sum
                    self.sum_mismatches.append({
                        "path": kou_path,
                        "year": year_key,
                        "level": "項→目",
                        "parent_value": parent_amount,
                        "children_sum": children_sum,
                        "difference": diff
                    })

                # 目の中の節もチェック
                self._check_moku_sums(kou_data["目"], kou_path, year_key)

    def _check_moku_sums(self, moku_list: list, path: str, year_key: str):
        """目レベルの合計チェック: 目のR8 == 子の節のR8の合計"""
        for i, moku_obj in enumerate(moku_list):
            if not isinstance(moku_obj, dict) or len(moku_obj) != 1:
                continue

            moku_name = list(moku_obj.keys())[0]
            moku_data = moku_obj[moku_name]
            moku_path = f"{path}/目[{i}]/{moku_name}"

            if not isinstance(moku_data, dict):
                continue

            parent_amount = self._get_amount(moku_data, year_key)

            # 節の合計を計算
            if "節" in moku_data and isinstance(moku_data["節"], list):
                children_sum = 0
                for setsu_obj in moku_data["節"]:
                    if isinstance(setsu_obj, dict) and len(setsu_obj) == 1:
                        setsu_name = list(setsu_obj.keys())[0]
                        setsu_data = setsu_obj[setsu_name]
                        if isinstance(setsu_data, dict):
                            children_sum += self._get_amount(setsu_data, year_key)

                if parent_amount != children_sum and parent_amount != 0:
                    diff = parent_amount - children_sum
                    self.sum_mismatches.append({
                        "path": moku_path,
                        "year": year_key,
                        "level": "目→節",
                        "parent_value": parent_amount,
                        "children_sum": children_sum,
                        "difference": diff
                    })

    # ========================================
    # 負の値チェック & Null値チェック
    # ========================================

    def validate_values(self, filepath: str) -> Tuple[List[dict], List[dict]]:
        """
        金額の妥当性とNull値をチェック

        Returns: (negative_values, null_issues)
        """
        self.negative_values = []
        self.null_issues = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.error(filepath, f"ファイル読み込みエラー: {e}")
            return [], []

        for section_key in ["歳入", "歳出"]:
            if section_key in data and "款" in data[section_key]:
                self._check_values_recursive(
                    data[section_key]["款"],
                    f"{section_key}",
                    "款"
                )

        return self.negative_values, self.null_issues

    def _check_values_recursive(self, items: list, path: str, level: str):
        """再帰的に金額とNull値をチェック"""
        child_level_map = {"款": "項", "項": "目", "目": "節", "節": None}
        child_key = child_level_map.get(level)

        for i, item_obj in enumerate(items):
            if not isinstance(item_obj, dict) or len(item_obj) != 1:
                continue

            item_name = list(item_obj.keys())[0]
            item_data = item_obj[item_name]
            item_path = f"{path}/{level}[{i}]/{item_name}"

            if not isinstance(item_data, dict):
                continue

            # R6/R7/R8 の値をチェック
            values = {}
            for year_key in ["R6", "R7", "R8"]:
                if year_key in item_data:
                    values[year_key] = item_data[year_key]

            # 負の値チェック
            for year_key, value in values.items():
                if isinstance(value, int) and value < 0:
                    self.negative_values.append({
                        "path": item_path,
                        "year": year_key,
                        "value": value
                    })

            # Null値チェック
            if values:
                all_null = all(v is None for v in values.values())
                some_null = any(v is None for v in values.values()) and not all_null
                null_years = [k for k, v in values.items() if v is None]

                if all_null:
                    # 全年度がnull → エラー
                    self.null_issues.append({
                        "path": item_path,
                        "type": "all_null",
                        "years": null_years,
                        "severity": "error"
                    })
                elif some_null:
                    # 特定年度のみnull → ワーニング
                    self.null_issues.append({
                        "path": item_path,
                        "type": "partial_null",
                        "years": null_years,
                        "severity": "warning"
                    })

            # 子階層を再帰的にチェック
            if child_key and child_key in item_data and isinstance(item_data[child_key], list):
                self._check_values_recursive(item_data[child_key], item_path, child_key)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="富士市予算書 JSON バリデーション",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python validate_json.py R8/json/*.json
  python validate_json.py merged_budget.json --check-sums
  python validate_json.py merged_budget.json --check-sums --year R8
        """
    )
    parser.add_argument("files", nargs="+", help="検証するJSONファイル")
    parser.add_argument(
        "--check-sums", "-s",
        action="store_true",
        help="階層間の合計値整合性をチェック (マージ済みJSON用)"
    )
    parser.add_argument(
        "--year", "-y",
        choices=["R6", "R7", "R8", "all"],
        default="all",
        help="チェックする年度 (デフォルト: all)"
    )
    parser.add_argument(
        "--sums-only",
        action="store_true",
        help="合計値チェックのみ実行 (構造バリデーションをスキップ)"
    )
    parser.add_argument(
        "--check-values", "-v",
        action="store_true",
        help="負の値チェックとNull値チェックを実行"
    )

    args = parser.parse_args()

    validator = BudgetJsonValidator(check_sums=args.check_sums)
    total_files = 0
    passed_files = 0
    all_errors = []
    all_mismatches = []
    all_negative_values = []
    all_null_issues = []

    for filepath in args.files:
        total_files += 1

        # 構造バリデーション (--sums-only でなければ実行)
        errors = []
        is_valid = True
        if not args.sums_only:
            is_valid, errors = validator.validate_file(filepath)
            all_errors.extend(errors)

        # 合計値チェック (--check-sums または --sums-only が指定された場合)
        mismatches = []
        if args.check_sums or args.sums_only:
            _, mismatches = validator.validate_merged_sums(filepath)
            # 年度フィルタ
            if args.year != "all":
                mismatches = [m for m in mismatches if m["year"] == args.year]
            all_mismatches.extend(mismatches)

        # 値チェック (--check-values が指定された場合)
        negative_values = []
        null_issues = []
        if args.check_values:
            negative_values, null_issues = validator.validate_values(filepath)
            # 年度フィルタ
            if args.year != "all":
                negative_values = [n for n in negative_values if n["year"] == args.year]
                null_issues = [n for n in null_issues if args.year in n["years"]]
            all_negative_values.extend(negative_values)
            all_null_issues.extend(null_issues)

        # 結果判定
        structure_ok = args.sums_only or is_valid
        sums_ok = len(mismatches) == 0
        values_ok = len(negative_values) == 0 and len([n for n in null_issues if n["severity"] == "error"]) == 0

        if structure_ok and sums_ok and values_ok:
            print(f"✓ {filepath}")
            passed_files += 1
        else:
            error_count = sum(1 for e in errors if e.severity == "error")
            warn_count = sum(1 for e in errors if e.severity == "warning")
            mismatch_count = len(mismatches)
            negative_count = len(negative_values)
            null_error_count = len([n for n in null_issues if n["severity"] == "error"])
            null_warn_count = len([n for n in null_issues if n["severity"] == "warning"])
            parts = []
            if error_count > 0:
                parts.append(f"{error_count} errors")
            if warn_count > 0:
                parts.append(f"{warn_count} warnings")
            if mismatch_count > 0:
                parts.append(f"{mismatch_count} sum mismatches")
            if negative_count > 0:
                parts.append(f"{negative_count} negative values")
            if null_error_count > 0:
                parts.append(f"{null_error_count} all-null errors")
            if null_warn_count > 0:
                parts.append(f"{null_warn_count} partial-null warnings")
            print(f"✗ {filepath} ({', '.join(parts)})")

    # サマリー
    print()
    print("=" * 60)
    print(f"結果: {passed_files}/{total_files} ファイル合格")

    # エラー詳細
    errors_only = [e for e in all_errors if e.severity == "error"]
    warnings_only = [e for e in all_errors if e.severity == "warning"]

    if errors_only:
        print(f"\n--- エラー ({len(errors_only)}件) ---")
        for err in errors_only[:30]:
            print(f"  {err}")
        if len(errors_only) > 30:
            print(f"  ... 他 {len(errors_only) - 30} 件")

    if warnings_only:
        print(f"\n--- 警告 ({len(warnings_only)}件) ---")
        for warn in warnings_only[:15]:
            print(f"  {warn}")
        if len(warnings_only) > 15:
            print(f"  ... 他 {len(warnings_only) - 15} 件")

    # 合計値不一致の詳細
    if all_mismatches:
        print(f"\n--- 合計値不一致 ({len(all_mismatches)}件) ---")
        for m in all_mismatches[:50]:
            print(f"  [{m['year']}] {m['path']}")
            print(f"       {m['level']}: 親={m['parent_value']:,} 子合計={m['children_sum']:,} 差={m['difference']:,}")
        if len(all_mismatches) > 50:
            print(f"  ... 他 {len(all_mismatches) - 50} 件")

    # 負の値の詳細
    if all_negative_values:
        print(f"\n--- 負の値 ({len(all_negative_values)}件) [ERROR] ---")
        for n in all_negative_values[:30]:
            print(f"  [{n['year']}] {n['path']}: {n['value']:,}")
        if len(all_negative_values) > 30:
            print(f"  ... 他 {len(all_negative_values) - 30} 件")

    # Null値の問題
    null_errors = [n for n in all_null_issues if n["severity"] == "error"]
    null_warnings = [n for n in all_null_issues if n["severity"] == "warning"]

    if null_errors:
        print(f"\n--- 全年度Null ({len(null_errors)}件) [ERROR] ---")
        for n in null_errors[:30]:
            print(f"  {n['path']}: 全年度がnull")
        if len(null_errors) > 30:
            print(f"  ... 他 {len(null_errors) - 30} 件")

    if null_warnings:
        print(f"\n--- 特定年度Null ({len(null_warnings)}件) [WARNING] ---")
        for n in null_warnings[:30]:
            print(f"  {n['path']}: {', '.join(n['years'])}がnull")
        if len(null_warnings) > 30:
            print(f"  ... 他 {len(null_warnings) - 30} 件")

    # 終了コード
    has_errors = len(errors_only) > 0
    has_mismatches = len(all_mismatches) > 0
    has_negative = len(all_negative_values) > 0
    has_null_errors = len(null_errors) > 0
    sys.exit(0 if (not has_errors and not has_mismatches and not has_negative and not has_null_errors) else 1)


if __name__ == "__main__":
    main()

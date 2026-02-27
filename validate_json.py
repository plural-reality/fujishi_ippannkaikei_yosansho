#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
富士市予算書 JSON バリデーション

README.md のルールに忠実に従い、JSON構造を検証する。

対応形式:
1. 個別款ファイル: {"款名": {本年度予算額, 前年度予算額, 項: [...]}}
2. 統合ファイル: {"歳入": {"款": [...]}, "歳出": {"款": [...]}}
3. 部分統合: {"款": [...]}

ルール:
1. 各レベル（款/項/目/節）は {名称: データ} 形式（単一キー）
2. 金額は整数（千円単位）
3. 説明の子項目は {名前: {金額: int, ...}} 形式
4. 計算式は "数値*数値%" のようなテキスト形式

使い方:
    python validate_json.py <json_file> [json_file2 ...]
    python validate_json.py R8/json/*.json
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

    def __init__(self):
        self.errors: List[ValidationError] = []

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


def main():
    if len(sys.argv) < 2:
        print("使い方: python validate_json.py <json_file> [json_file2 ...]")
        print("例: python validate_json.py R8/json/*.json")
        sys.exit(1)

    validator = BudgetJsonValidator()
    total_files = 0
    passed_files = 0
    all_errors = []

    for filepath in sys.argv[1:]:
        total_files += 1
        is_valid, errors = validator.validate_file(filepath)

        if is_valid:
            print(f"✓ {filepath}")
            passed_files += 1
        else:
            error_count = sum(1 for e in errors if e.severity == "error")
            warn_count = sum(1 for e in errors if e.severity == "warning")
            print(f"✗ {filepath} ({error_count} errors, {warn_count} warnings)")

        all_errors.extend(errors)

    # サマリー
    print()
    print("=" * 50)
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

    sys.exit(0 if passed_files == total_files else 1)


if __name__ == "__main__":
    main()

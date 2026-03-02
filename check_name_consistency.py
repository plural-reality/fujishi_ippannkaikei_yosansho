#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
名称一貫性チェック（LLM利用）

merged_budget.json 内の名称を抽出し、
同じ階層内（歳入/歳出 x 款/項/目/節）で表記ゆれがないかをLLMでチェックします。

使い方:
    python check_name_consistency.py merged_budget.json
    python check_name_consistency.py merged_budget.json --output report.json
    python check_name_consistency.py merged_budget.json --validate-only

環境変数:
    OPENROUTER_API_KEY: OpenRouter API キー
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Set, Tuple
from collections import defaultdict

try:
    from dotenv import load_dotenv
    # .env ファイルを読み込み（スクリプトと同じディレクトリ）
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv がなくても環境変数から直接読める

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai パッケージが必要です")
    print("インストール: pip install openai")
    sys.exit(1)

# OpenRouter経由で使用するモデル
DEFAULT_MODEL = "anthropic/claude-opus-4"


def validate_key_object_structure(data: dict) -> List[Dict]:
    """
    配列の各要素が {key: object} 構造になっているかを検証

    Returns:
        問題のあるエントリのリスト
    """
    issues = []

    for section_key in ["歳入", "歳出"]:
        if section_key not in data:
            continue

        section = data[section_key]
        if "款" not in section:
            continue

        for i, kan_obj in enumerate(section["款"]):
            path = f"{section_key}/款[{i}]"
            issue = _check_key_object(kan_obj, path, "款")
            if issue:
                issues.append(issue)
                continue

            kan_name = list(kan_obj.keys())[0]
            kan_data = kan_obj[kan_name]

            if isinstance(kan_data, dict) and "項" in kan_data:
                for j, kou_obj in enumerate(kan_data["項"]):
                    path = f"{section_key}/款/{kan_name}/項[{j}]"
                    issue = _check_key_object(kou_obj, path, "項")
                    if issue:
                        issues.append(issue)
                        continue

                    kou_name = list(kou_obj.keys())[0]
                    kou_data = kou_obj[kou_name]

                    if isinstance(kou_data, dict) and "目" in kou_data:
                        for k, moku_obj in enumerate(kou_data["目"]):
                            path = f"{section_key}/款/{kan_name}/項/{kou_name}/目[{k}]"
                            issue = _check_key_object(moku_obj, path, "目")
                            if issue:
                                issues.append(issue)
                                continue

                            moku_name = list(moku_obj.keys())[0]
                            moku_data = moku_obj[moku_name]

                            if isinstance(moku_data, dict) and "節" in moku_data:
                                for l, setsu_obj in enumerate(moku_data["節"]):
                                    path = f"{section_key}/款/{kan_name}/項/{kou_name}/目/{moku_name}/節[{l}]"
                                    issue = _check_key_object(setsu_obj, path, "節")
                                    if issue:
                                        issues.append(issue)

    return issues


def _check_key_object(obj, path: str, level: str) -> Dict | None:
    """単一オブジェクトが {key: object} 構造かチェック"""
    if not isinstance(obj, dict):
        return {
            "path": path,
            "level": level,
            "issue": "dict ではない",
            "actual_type": type(obj).__name__,
            "value": str(obj)[:100]
        }

    if len(obj) == 0:
        return {
            "path": path,
            "level": level,
            "issue": "空のdict",
            "value": "{}"
        }

    if len(obj) != 1:
        return {
            "path": path,
            "level": level,
            "issue": f"キーが {len(obj)} 個ある（1個であるべき）",
            "keys": list(obj.keys())
        }

    key = list(obj.keys())[0]
    value = obj[key]

    if not isinstance(key, str):
        return {
            "path": path,
            "level": level,
            "issue": "キーが文字列ではない",
            "key_type": type(key).__name__
        }

    if not isinstance(value, dict):
        return {
            "path": path,
            "level": level,
            "issue": "値がdictではない",
            "key": key,
            "value_type": type(value).__name__
        }

    return None


def extract_names(data: dict, path: str = "") -> List[Dict]:
    """JSONから全ての名称を抽出"""
    names = []

    for section_key in ["歳入", "歳出"]:
        if section_key not in data:
            continue

        section = data[section_key]
        if "款" not in section:
            continue

        for i, kan_obj in enumerate(section["款"]):
            if not isinstance(kan_obj, dict) or len(kan_obj) != 1:
                continue

            kan_name = list(kan_obj.keys())[0]
            kan_data = kan_obj[kan_name]
            kan_path = f"{section_key}/款[{i}]"

            names.append({
                "name": kan_name,
                "level": "款",
                "path": kan_path,
                "section": section_key
            })

            if isinstance(kan_data, dict) and "項" in kan_data:
                for j, kou_obj in enumerate(kan_data["項"]):
                    if not isinstance(kou_obj, dict) or len(kou_obj) != 1:
                        continue

                    kou_name = list(kou_obj.keys())[0]
                    kou_data = kou_obj[kou_name]
                    kou_path = f"{kan_path}/{kan_name}/項[{j}]"

                    names.append({
                        "name": kou_name,
                        "level": "項",
                        "path": kou_path,
                        "parent": kan_name,
                        "section": section_key
                    })

                    if isinstance(kou_data, dict) and "目" in kou_data:
                        for k, moku_obj in enumerate(kou_data["目"]):
                            if not isinstance(moku_obj, dict) or len(moku_obj) != 1:
                                continue

                            moku_name = list(moku_obj.keys())[0]
                            moku_data = moku_obj[moku_name]
                            moku_path = f"{kou_path}/{kou_name}/目[{k}]"

                            names.append({
                                "name": moku_name,
                                "level": "目",
                                "path": moku_path,
                                "parent": kou_name,
                                "section": section_key
                            })

                            if isinstance(moku_data, dict) and "節" in moku_data:
                                for l, setsu_obj in enumerate(moku_data["節"]):
                                    if not isinstance(setsu_obj, dict) or len(setsu_obj) != 1:
                                        continue

                                    setsu_name = list(setsu_obj.keys())[0]
                                    setsu_path = f"{moku_path}/{moku_name}/節[{l}]"

                                    names.append({
                                        "name": setsu_name,
                                        "level": "節",
                                        "path": setsu_path,
                                        "parent": moku_name,
                                        "section": section_key
                                    })

    return names


def group_names_by_section_and_level(names: List[Dict]) -> Dict[Tuple[str, str], List[Dict]]:
    """
    歳入/歳出 と 款/項/目/節 の組み合わせでグループ化

    同じ階層内（例：歳入の款、歳出の項など）での比較が重要なため、
    セクションとレベルの両方でグループ化する
    """
    grouped = defaultdict(list)
    for name_info in names:
        key = (name_info["section"], name_info["level"])
        grouped[key].append(name_info)
    return dict(grouped)


def check_consistency_with_llm(
    names_by_section_level: Dict[Tuple[str, str], List[Dict]],
    client: OpenAI,
    model: str
) -> List[Dict]:
    """
    LLMを使って名称の一貫性をチェック

    同じ階層内（歳入/歳出 x 款/項/目/節）で表記ゆれを検出する
    """
    issues = []

    for (section, level), name_infos in sorted(names_by_section_level.items()):
        # ユニークな名称を抽出
        unique_names = sorted(set(info["name"] for info in name_infos))

        if len(unique_names) < 2:
            continue

        print(f"  [{section}] {level}レベルをチェック中... ({len(unique_names)}種類)")

        # 名称リストをチャンクに分割（APIの制限対策）
        chunk_size = 100
        for chunk_start in range(0, len(unique_names), chunk_size):
            chunk = unique_names[chunk_start:chunk_start + chunk_size]

            prompt = f"""以下は日本の市区町村予算書における「{section}」の「{level}」レベルの項目名リストです。
**同じ階層内で**、表記ゆれや部分一致により別のキーになっている可能性があるものを検出してください。

## 検出してほしいパターン

1. **スペースの有無や位置の違い**
   - 「市税」と「市 税」
   - 「土地」と「土 地」
   - 「シティプロモーション」と「シティ プロ」

2. **括弧付き・括弧なしの違い**
   - 「滞納繰越分」と「滞納繰越分(今年度)」
   - 「現年課税分」と「現年課税分（令和5年度）」

3. **略称と正式名称**
   - 「男女共同参」と「男女共同参画」
   - 「消費税」と「消費税及び地方消費税」

4. **全角/半角の違い**
   - 「令和5年度」と「令和５年度」

5. **OCR由来の誤認識**
   - 文字化けや類似文字の誤認識

## 名称リスト
{json.dumps(chunk, ensure_ascii=False, indent=2)}

## 回答形式（JSON配列）
[
  {{
    "names": ["名称1", "名称2"],
    "reason": "類似の理由を具体的に説明",
    "confidence": "high/medium/low"
  }}
]

- **high**: 明らかに同一項目の表記ゆれ
- **medium**: 同一項目の可能性が高い
- **low**: 関連がありそうだが確証がない

類似がない場合は空の配列 [] を返してください。
JSONのみ返してください。"""

            try:
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )

                response_text = response.choices[0].message.content.strip()

                # JSON部分を抽出
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                similar_groups = json.loads(response_text)

                for group in similar_groups:
                    # 各名称の出現箇所を追加
                    locations = []
                    for name in group.get("names", []):
                        for info in name_infos:
                            if info["name"] == name:
                                locations.append({
                                    "name": name,
                                    "path": info["path"],
                                    "section": info["section"]
                                })

                    if locations:
                        issues.append({
                            "section": section,
                            "level": level,
                            "similar_names": group.get("names", []),
                            "reason": group.get("reason", ""),
                            "confidence": group.get("confidence", "medium"),
                            "locations": locations
                        })

            except json.JSONDecodeError as e:
                print(f"Warning: LLM応答のJSONパースに失敗: {e}")
            except Exception as e:
                print(f"Warning: API呼び出しエラー: {e}")

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="名称一貫性チェック（LLM利用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python check_name_consistency.py merged_budget.json
  python check_name_consistency.py merged_budget.json --output report.json
  python check_name_consistency.py merged_budget.json --model anthropic/claude-sonnet-4
  python check_name_consistency.py merged_budget.json --validate-only
        """
    )
    parser.add_argument("file", help="チェックするJSONファイル")
    parser.add_argument("--output", "-o", help="結果をJSONファイルに出力")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        help=f"使用するモデル (デフォルト: {DEFAULT_MODEL})")
    parser.add_argument("--validate-only", "-v", action="store_true",
                        help="構造検証のみ実行（LLMチェックをスキップ）")

    args = parser.parse_args()

    # JSONファイル読み込み
    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: ファイルが見つかりません: {args.file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: JSONパースエラー: {e}")
        sys.exit(1)

    # 構造検証を実行
    print(f"\n構造検証中: {args.file}")
    structure_issues = validate_key_object_structure(data)

    if structure_issues:
        print(f"\n" + "=" * 60)
        print(f"構造検証エラー: {len(structure_issues)} 件")
        print("=" * 60)
        print("配列の各要素は {key: object} 形式である必要があります。\n")

        for i, issue in enumerate(structure_issues, 1):
            print(f"{i}. [{issue['level']}] {issue['path']}")
            print(f"   問題: {issue['issue']}")
            if "keys" in issue:
                print(f"   キー: {issue['keys']}")
            if "value" in issue:
                print(f"   値: {issue['value']}")
            if "actual_type" in issue:
                print(f"   実際の型: {issue['actual_type']}")
            print()

        if args.output:
            result = {
                "file": args.file,
                "structure_issues": structure_issues,
                "structure_valid": False
            }
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"結果を保存しました: {args.output}")

        sys.exit(1)
    else:
        print("  構造検証: OK (全ての配列要素が {key: object} 形式)")

    # --validate-only の場合はここで終了
    if args.validate_only:
        print("\n構造検証が完了しました。")
        sys.exit(0)

    print(f"\n名称を抽出中: {args.file}")
    names = extract_names(data)
    print(f"  抽出した名称数: {len(names)}")

    names_by_section_level = group_names_by_section_and_level(names)
    for (section, level), infos in sorted(names_by_section_level.items()):
        unique_count = len(set(info["name"] for info in infos))
        print(f"  [{section}] {level}: {unique_count} 種類 ({len(infos)} 箇所)")

    # API キーの確認（LLMチェック時のみ）
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("\nError: OPENROUTER_API_KEY 環境変数を設定してください")
        print("  .env ファイルに書くか、export OPENROUTER_API_KEY=... で設定")
        sys.exit(1)

    print(f"\nLLMで名称の一貫性をチェック中... (モデル: {args.model})")
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    issues = check_consistency_with_llm(names_by_section_level, client, args.model)

    # 結果出力
    print("\n" + "=" * 60)
    print(f"検出された表記ゆれ: {len(issues)} 件")
    print("=" * 60)

    if issues:
        for i, issue in enumerate(issues, 1):
            confidence_marker = {
                "high": "[HIGH]",
                "medium": "[MED]",
                "low": "[LOW]"
            }.get(issue["confidence"], "[?]")

            section = issue.get("section", "?")
            level = issue.get("level", "?")
            print(f"\n{i}. {confidence_marker} [{section}] {level}: {' ↔ '.join(issue['similar_names'])}")
            print(f"   理由: {issue['reason']}")
            print(f"   出現箇所:")
            for loc in issue["locations"][:5]:
                print(f"     - {loc['path']}")
            if len(issue["locations"]) > 5:
                print(f"     ... 他 {len(issue['locations']) - 5} 箇所")
    else:
        print("\n表記ゆれは検出されませんでした。")

    # JSON出力
    if args.output:
        result = {
            "file": args.file,
            "structure_valid": True,
            "total_names": len(names),
            "names_by_section_level": {
                f"{section}/{level}": len(set(info["name"] for info in infos))
                for (section, level), infos in names_by_section_level.items()
            },
            "issues_count": len(issues),
            "issues": issues
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n結果を保存しました: {args.output}")

    sys.exit(0 if len(issues) == 0 else 1)


if __name__ == "__main__":
    main()

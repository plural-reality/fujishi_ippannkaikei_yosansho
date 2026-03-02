#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
予算書PDF座標ベース抽出スクリプト v4
見開きページをY座標でマッチング + 節の説明詳細を抽出
"""

import pdfplumber
import json
import re
from collections import defaultdict
from typing import List, Dict, Tuple, Optional


SAINYUU_PAGES = (28, 175)
SAISHUTSU_PAGES = (176, 596)


def extract_right_page_setsu(pdf, page_num: int) -> List[Dict]:
    """
    右ページから節データを詳細に抽出

    Returns:
        [{"節名": str, "金額": int, "説明": {...}, "y_start": float}, ...]
    """
    if page_num >= len(pdf.pages):
        return []

    page = pdf.pages[page_num]
    words = page.extract_words()

    # Y座標でグループ化（5px単位）
    y_groups = defaultdict(list)
    for w in words:
        y = round(w['top'] / 5) * 5
        y_groups[y].append(w)

    # 行をY座標順にソート
    lines = []
    for y in sorted(y_groups.keys()):
        texts = [w['text'] for w in sorted(y_groups[y], key=lambda w: w['x0'])]
        line_text = ' '.join(texts)
        lines.append({'y': y, 'text': line_text})

    # 節の開始を検出してグループ化
    setsu_groups = []
    current_setsu = None

    for line in lines:
        text = line['text']
        y = line['y']

        # ヘッダー行はスキップ
        if '節' in text and '説' in text:
            continue
        if '区 分' in text or '金 額' in text:
            continue
        if text.strip() in ['千円', '千円 千円']:
            continue
        if re.match(r'^-\s*\d+\s*-$', text):
            continue

        # 節の開始パターン: "番号 名称 金額 ..."
        setsu_match = re.match(r'^(\d+)\s+([^\d\s]+(?:\s*[^\d\s]+)*?)\s+([\d,]+)\s+(.*)$', text)
        if setsu_match:
            # 新しい節の開始
            if current_setsu:
                setsu_groups.append(current_setsu)

            setsu_name = setsu_match.group(2).replace(' ', '')
            setsu_amount = int(setsu_match.group(3).replace(',', ''))  # 千円単位のまま
            remaining = setsu_match.group(4)

            current_setsu = {
                '節名': setsu_name,
                '金額': setsu_amount,
                'y_start': y,
                '説明_lines': [remaining] if remaining.strip() else [],
            }
        elif current_setsu:
            # 現在の節に説明行を追加
            current_setsu['説明_lines'].append(text)

    if current_setsu:
        setsu_groups.append(current_setsu)

    # 説明行をパースして構造化
    result = []
    for setsu in setsu_groups:
        parsed_setsu = {
            '節名': setsu['節名'],
            '金額': setsu['金額'],
            'y_start': setsu['y_start'],
            '説明': parse_setsumei_lines(setsu['説明_lines'], setsu['節名']),
        }
        result.append(parsed_setsu)

    return result


def parse_setsumei_lines(lines: List[str], setsu_name: str) -> Dict:
    """
    説明行をパースして構造化

    例:
    ["現年課税分 14,181,000", "均等割 397,000", "調定見込額 402,000×98.9％", ...]
    → {"均等割": {"金額": 397000000, "調定見込額": "..."}, "所得割": {...}}
    """
    result = {}
    current_item_name = None
    setsu_level_info = {}  # 節レベルの情報（子項目がない場合用）

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 調定見込額パターン
        if '調定見込額' in line or '算定標準額' in line:
            key = '調定見込額' if '調定見込額' in line else '算定標準額'
            value = line.replace('調定見込額', '').replace('算定標準額', '').strip()
            if current_item_name and current_item_name in result:
                result[current_item_name][key] = value
            else:
                # 子項目がない場合は節レベルに追加
                setsu_level_info[key] = value
            continue

        # 金額付き項目パターン: "名称 金額"
        item_match = re.match(r'^([^\d]+?)\s*([\d,]+)$', line)
        if item_match:
            item_name = item_match.group(1).strip()
            item_amount = int(item_match.group(2).replace(',', ''))  # 千円単位のまま

            # 節名と同じ名前はスキップ（重複防止）
            if item_name == setsu_name:
                current_item_name = None  # 次の調定見込額は節レベルへ
                continue
            # 同じ名前が既にある場合もスキップ
            if item_name not in result:
                result[item_name] = {'金額': item_amount}
                current_item_name = item_name
            continue

        # その他の行（備考として追加）
        if current_item_name and current_item_name in result:
            if '備考' not in result[current_item_name]:
                result[current_item_name]['備考'] = line
            else:
                result[current_item_name]['備考'] += ' ' + line

    # 節レベルの情報をマージ
    if setsu_level_info and not result:
        result = setsu_level_info
    elif setsu_level_info:
        result['_節情報'] = setsu_level_info

    return result


def extract_spread_rows(pdf, left_page_num: int, right_page_num: int, y_tolerance: int = 12) -> List[Dict]:
    """見開き2ページをY座標でマッチングして行データを抽出"""
    if left_page_num >= len(pdf.pages) or right_page_num >= len(pdf.pages):
        return []

    left_page = pdf.pages[left_page_num]
    right_page = pdf.pages[right_page_num]

    left_words = left_page.extract_words()
    right_words = right_page.extract_words()

    page_width = left_page.width

    for w in left_words:
        w['source'] = 'left'
    for w in right_words:
        w['source'] = 'right'
        w['x0'] += page_width

    all_words = left_words + right_words

    y_groups = defaultdict(list)
    for w in all_words:
        y = round(w['top'] / y_tolerance) * y_tolerance
        y_groups[y].append(w)

    rows = []
    for y in sorted(y_groups.keys()):
        words = sorted(y_groups[y], key=lambda w: w['x0'])
        left_texts = [w['text'] for w in words if w['source'] == 'left']
        right_texts = [w['text'] for w in words if w['source'] == 'right']

        rows.append({
            'y': y,
            'left': ' '.join(left_texts),
            'right': ' '.join(right_texts),
        })

    return rows


def parse_amount(text: str) -> Optional[int]:
    """金額文字列をパース（千円単位のまま）"""
    if not text:
        return None
    text = text.replace(',', '').replace('△', '-').replace('千円', '').strip()
    try:
        return int(text)  # 千円単位のまま
    except:
        return None


def identify_row_type(left_text: str) -> Tuple[str, Optional[str], Optional[Dict]]:
    """左側テキストから行タイプを識別"""
    left_text = left_text.strip()

    if not left_text:
        return ('empty', None, None)

    if '本年度予算額' in left_text or '前年度予算額' in left_text:
        return ('header', None, None)
    if left_text in ['千円', '千円 千円 千円']:
        return ('header', None, None)
    if re.match(r'^-\s*\d+\s*-$', left_text):
        return ('page_number', None, None)

    kan_match = re.match(r'[（(]?(\d+|[０-９]+)款\s+(.+?)\s+([\d,]+)千円', left_text)
    if kan_match:
        return ('kan_header', kan_match.group(2), {
            '番号': kan_match.group(1),
            '本年度予算額': parse_amount(kan_match.group(3)),
        })

    kou_match = re.match(r'(\d+|[０-９]+)項\s+(.+?)\s+([\d,]+)千円', left_text)
    if kou_match:
        return ('kou_header', kou_match.group(2), {
            '番号': kou_match.group(1),
            '本年度予算額': parse_amount(kou_match.group(3)),
        })

    total_match = re.match(r'計\s+([\d,△\-]+)\s+([\d,△\-]+)\s+([\d,△\-]+)', left_text)
    if total_match:
        return ('total', None, {
            '本年度予算額': parse_amount(total_match.group(1)),
            '前年度予算額': parse_amount(total_match.group(2)),
            '比較': parse_amount(total_match.group(3)),
        })

    moku_match = re.match(r'(\d+)\s+(.+?)\s+([\d,△\-]+)\s+([\d,△\-]+)\s+([\d,△\-]+)', left_text)
    if moku_match:
        return ('moku', moku_match.group(2), {
            '番号': moku_match.group(1),
            '本年度予算額': parse_amount(moku_match.group(3)),
            '前年度予算額': parse_amount(moku_match.group(4)),
            '比較': parse_amount(moku_match.group(5)),
        })

    return ('unknown', left_text, None)


def build_budget_structure(pdf, start_page: int, end_page: int) -> Dict:
    """指定ページ範囲から予算構造を構築"""
    result = {"款": []}

    current_kan = None
    current_kou = None

    for left_idx in range(start_page - 1, end_page - 1, 2):
        right_idx = left_idx + 1
        if right_idx >= len(pdf.pages):
            break

        # 左ページから款・項・目を抽出
        left_rows = extract_spread_rows(pdf, left_idx, right_idx)

        # 右ページから節の詳細を抽出
        right_setsu_list = extract_right_page_setsu(pdf, right_idx)

        # 目の行とそのY座標を収集
        moku_rows = []
        for row in left_rows:
            row_type, name, data = identify_row_type(row['left'])
            if row_type == 'moku':
                moku_rows.append({'y': row['y'], 'name': name, 'data': data, 'row': row})

        for row in left_rows:
            row_type, name, data = identify_row_type(row['left'])

            if row_type == 'kan_header':
                kan_name = name
                if current_kan is None or list(current_kan.keys())[0] != kan_name:
                    if current_kan:
                        result['款'].append(current_kan)
                    current_kan = {
                        kan_name: {
                            '本年度予算額': data.get('本年度予算額'),
                            '項': []
                        }
                    }
                    current_kou = None

            elif row_type == 'kou_header':
                kou_name = name
                if current_kan:
                    kan_name = list(current_kan.keys())[0]
                    existing = None
                    for k in current_kan[kan_name]['項']:
                        if list(k.keys())[0] == kou_name:
                            existing = k
                            break

                    if existing is None:
                        current_kou = {
                            kou_name: {
                                '本年度予算額': data.get('本年度予算額'),
                                '目': []
                            }
                        }
                        current_kan[kan_name]['項'].append(current_kou)
                    else:
                        current_kou = existing

            elif row_type == 'moku':
                moku_name = name
                if current_kou:
                    kou_name = list(current_kou.keys())[0]

                    moku_data = {
                        '本年度予算額': data.get('本年度予算額'),
                        '前年度予算額': data.get('前年度予算額'),
                        '比較': data.get('比較'),
                    }

                    # 現在の目のY座標範囲を計算
                    row_y = row['y']
                    # 次の目のY座標を探す
                    next_moku_y = float('inf')
                    for mr in moku_rows:
                        if mr['y'] > row_y:
                            next_moku_y = mr['y']
                            break

                    # Y座標範囲内の節を全て収集
                    matched_setsu = []
                    remaining_setsu = []
                    for setsu in right_setsu_list:
                        if row_y - 20 <= setsu['y_start'] < next_moku_y - 20:
                            matched_setsu.append(setsu)
                        else:
                            remaining_setsu.append(setsu)
                    right_setsu_list = remaining_setsu

                    if matched_setsu:
                        moku_data['節'] = []
                        for s in matched_setsu:
                            setsu_entry = {
                                s['節名']: {
                                    '金額': s['金額'],
                                }
                            }
                            if s['説明']:
                                setsu_entry[s['節名']]['説明'] = s['説明']
                            moku_data['節'].append(setsu_entry)

                    moku_entry = {moku_name: moku_data}
                    current_kou[kou_name]['目'].append(moku_entry)

    if current_kan:
        result['款'].append(current_kan)

    return result


def main():
    import sys

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "bugget.pdf"
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    with pdfplumber.open(pdf_path) as pdf:
        print(f"PDF: {pdf_path}", file=sys.stderr)
        print(f"総ページ数: {len(pdf.pages)}", file=sys.stderr)

        print("歳入を抽出中...", file=sys.stderr)
        sainyuu = build_budget_structure(pdf, SAINYUU_PAGES[0], SAINYUU_PAGES[1])
        print(f"  歳入: {len(sainyuu['款'])}款", file=sys.stderr)

        print("歳出を抽出中...", file=sys.stderr)
        saishutsu = build_budget_structure(pdf, SAISHUTSU_PAGES[0], SAISHUTSU_PAGES[1])
        print(f"  歳出: {len(saishutsu['款'])}款", file=sys.stderr)

        result = {
            "歳入": sainyuu,
            "歳出": saishutsu,
        }

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"出力: {output_path}", file=sys.stderr)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

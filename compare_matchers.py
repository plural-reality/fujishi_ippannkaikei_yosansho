#!/usr/bin/env python3
"""
Compare matcher results: strict vs loose.
Output:
1. Keys that get merged by loose (different strict IDs → same loose ID)
2. Keys that still don't match across years even with loose
"""

from __future__ import annotations

from collections import defaultdict

from budget_cell.excel_io import read_rows_from_excel_path
from budget_cell.matchers import MATCHERS
from budget_cell.trend import TrendKey, rows_to_trend_nodes


def load_nodes(year_to_path: dict[str, str]):
    """Load trend nodes from Excel files."""
    all_nodes = []
    for year, path in year_to_path.items():
        rows = read_rows_from_excel_path(path)
        nodes = rows_to_trend_nodes(year, rows)
        all_nodes.extend(nodes)
    return all_nodes


def format_key(key: TrendKey) -> str:
    """Format TrendKey for display."""
    path = " > ".join(key.path_levels) if key.path_levels else "(no path)"
    return f"{key.kan_name} | {key.kou_name} | {key.moku_name} | {path}"


def main():
    # Input files - R6 and R8
    year_to_path = {
        "R6": "R6/bugget_spread_cover1_long_v3.xlsx",
        "R8": "R8/bugget_setsumei_long_ffill.xlsx",
    }

    print("Loading data...")
    nodes = load_nodes(year_to_path)
    all_years = set(year_to_path.keys())
    print(f"  Loaded {len(nodes)} nodes from {len(all_years)} years")

    strict_fn = MATCHERS["strict"]
    loose_fn = MATCHERS["loose"]

    # Group by loose match ID
    loose_to_strict: dict[str, set[str]] = defaultdict(set)
    loose_to_keys: dict[str, list[tuple[str, TrendKey]]] = defaultdict(list)
    strict_to_years: dict[str, set[str]] = defaultdict(set)
    loose_to_years: dict[str, set[str]] = defaultdict(set)

    for node in nodes:
        strict_id = strict_fn(node.key)
        loose_id = loose_fn(node.key)
        loose_to_strict[loose_id].add(strict_id)
        loose_to_keys[loose_id].append((node.year, node.key))
        strict_to_years[strict_id].add(node.year)
        loose_to_years[loose_id].add(node.year)

    # 1. Keys that get merged (multiple strict IDs → same loose ID)
    merged = []
    for loose_id, strict_ids in loose_to_strict.items():
        if len(strict_ids) > 1:
            keys_by_year = defaultdict(list)
            for year, key in loose_to_keys[loose_id]:
                keys_by_year[year].append(key)
            merged.append({
                "loose_id": loose_id,
                "strict_ids": sorted(strict_ids),
                "keys_by_year": dict(keys_by_year),
                "years": loose_to_years[loose_id],
            })

    # 2. Keys where loose achieves cross-year match but strict doesn't
    improved = []
    for loose_id, strict_ids in loose_to_strict.items():
        if loose_to_years[loose_id] == all_years:
            # Check if any strict ID didn't have all years
            if any(strict_to_years[sid] != all_years for sid in strict_ids):
                improved.append({
                    "loose_id": loose_id,
                    "strict_ids": sorted(strict_ids),
                    "keys": [key for _, key in loose_to_keys[loose_id]],
                })

    # 3. Keys that still don't match
    still_unmatched = []
    for loose_id, years in loose_to_years.items():
        if years != all_years:
            still_unmatched.append({
                "loose_id": loose_id,
                "years_found": sorted(years),
                "years_missing": sorted(all_years - years),
                "keys": [key for _, key in loose_to_keys[loose_id][:3]],
            })

    # Output
    print(f"\n{'='*80}")
    print(f"1. 表記ゆれで統合されたもの (異なるstrict ID → 同じloose ID): {len(merged)} 件")
    print(f"{'='*80}")

    for i, item in enumerate(sorted(merged, key=lambda x: -len(x["strict_ids"]))[:30], 1):
        print(f"\n[{i}] loose_id: {item['loose_id'][:70]}...")
        print(f"  strict IDs ({len(item['strict_ids'])}):")
        for sid in item["strict_ids"][:5]:
            print(f"    - {sid[:70]}")
        if len(item["strict_ids"]) > 5:
            print(f"    ... and {len(item['strict_ids']) - 5} more")
        print(f"  years: {sorted(item['years'])}")

    if len(merged) > 30:
        print(f"\n... and {len(merged) - 30} more")

    print(f"\n{'='*80}")
    print(f"2. looseで年度跨ぎマッチが改善されたもの: {len(improved)} 件")
    print(f"{'='*80}")

    for i, item in enumerate(improved[:20], 1):
        print(f"\n[{i}] loose_id: {item['loose_id'][:70]}...")
        print(f"  Merged from {len(item['strict_ids'])} strict IDs")
        for key in item["keys"][:2]:
            print(f"  Key: {format_key(key)}")

    if len(improved) > 20:
        print(f"\n... and {len(improved) - 20} more")

    print(f"\n{'='*80}")
    print(f"3. looseでもマッチしなかったもの: {len(still_unmatched)} 件")
    print(f"{'='*80}")

    for i, item in enumerate(still_unmatched[:20], 1):
        print(f"\n[{i}] loose_id: {item['loose_id'][:70]}...")
        print(f"  存在: {item['years_found']}, 欠落: {item['years_missing']}")
        for key in item["keys"]:
            print(f"  Key: {format_key(key)}")

    if len(still_unmatched) > 20:
        print(f"\n... and {len(still_unmatched) - 20} more")

    # Summary
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"Total unique strict IDs: {len(strict_to_years)}")
    print(f"Total unique loose IDs: {len(loose_to_years)}")
    print(f"Merged by loose: {len(merged)} groups ({sum(len(m['strict_ids']) for m in merged) - len(merged)} IDs reduced)")
    print(f"Cross-year match improved: {len(improved)} items")
    print(f"Still unmatched: {len(still_unmatched)} items")

    strict_full = sum(1 for y in strict_to_years.values() if y == all_years)
    loose_full = sum(1 for y in loose_to_years.values() if y == all_years)
    print(f"\nStrict: {strict_full} IDs match all years")
    print(f"Loose:  {loose_full} IDs match all years")

    # Write to file
    write_to_file(still_unmatched, merged, improved)


def write_to_file(still_unmatched, merged, improved, output_path="matcher_comparison_result.txt"):
    """Write results to file."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"1. 新たにマッチするようになったもの（表記ゆれ統合）: {len(merged)} 件\n")
        f.write("=" * 80 + "\n\n")

        for i, item in enumerate(sorted(merged, key=lambda x: -len(x["strict_ids"])), 1):
            f.write(f"[{i}] loose_id: {item['loose_id']}\n")
            f.write(f"  strict IDs ({len(item['strict_ids'])}):\n")
            for sid in item["strict_ids"]:
                f.write(f"    - {sid}\n")
            f.write(f"  years: {sorted(item['years'])}\n\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write(f"2. それでもマッチしなかったもの: {len(still_unmatched)} 件\n")
        f.write("=" * 80 + "\n\n")

        for i, item in enumerate(still_unmatched, 1):
            f.write(f"[{i}] loose_id: {item['loose_id']}\n")
            f.write(f"  存在: {item['years_found']}, 欠落: {item['years_missing']}\n")
            for key in item["keys"]:
                path = " > ".join(key.path_levels) if key.path_levels else "(no path)"
                f.write(f"  Key: {key.kan_name} | {key.kou_name} | {key.moku_name} | {path}\n")
            f.write("\n")

    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()

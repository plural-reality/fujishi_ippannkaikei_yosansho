"""
CLI: build side-by-side spread PDF from single-page source PDF.
"""

from __future__ import annotations

import argparse
import sys

from budget_cell.spread import build_spread_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m budget_cell.cli.make_spread",
        description="Create spread PDF (2-up) from single-page PDF.",
    )
    parser.add_argument("src", help="input PDF path")
    parser.add_argument("dst", help="output spread PDF path")
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="1-based first page to include (default: 1)",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="1-based last page to include (default: EOF)",
    )
    parser.add_argument(
        "--reverse-pairs",
        action="store_true",
        help="swap left/right order within each page pair",
    )
    parser.add_argument(
        "--head-single-pages",
        type=int,
        default=0,
        help="number of leading pages to keep as single pages before pairing",
    )
    args = parser.parse_args(sys.argv[1:])

    stats = build_spread_pdf(
        args.src,
        args.dst,
        start_page=args.start_page,
        end_page=args.end_page,
        reverse_pairs=args.reverse_pairs,
        head_single_pages=args.head_single_pages,
    )
    print(
        f"spread created: {args.dst} "
        f"(src_pages={stats.src_pages}, used_pages={stats.used_pages}, "
        f"dst_pages={stats.dst_pages}, head_single={stats.head_single}, "
        f"paired={stats.paired}, single_tail={stats.single_tail})"
    )


if __name__ == "__main__":
    main()

"""
PDF spread builder.

Converts single-page sequence into side-by-side spread pages (2-up).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpreadStats:
    src_pages: int
    used_pages: int
    dst_pages: int
    head_single: int
    paired: int
    single_tail: int


def build_spread_pdf(
    src_path: str,
    dst_path: str,
    start_page: int = 1,
    end_page: int | None = None,
    reverse_pairs: bool = False,
    head_single_pages: int = 0,
) -> SpreadStats:
    import fitz

    src = fitz.open(src_path)
    src_page_count = src.page_count
    dst = fitz.open()
    start_idx = max(start_page - 1, 0)
    end_idx = src_page_count if end_page is None else min(end_page, src_page_count)
    indices = tuple(range(start_idx, end_idx))
    head_count = max(min(head_single_pages, len(indices)), 0)
    head_indices = indices[:head_count]
    pair_indices = indices[head_count:]

    for page_index in head_indices:
        source = src[page_index]
        rect = source.rect
        page = dst.new_page(width=rect.width, height=rect.height)
        page.show_pdf_page(fitz.Rect(0, 0, rect.width, rect.height), src, page_index)

    for left_index in range(0, len(pair_indices), 2):
        right_index = left_index + 1
        left_source = (
            pair_indices[right_index]
            if reverse_pairs and right_index < len(pair_indices)
            else pair_indices[left_index]
        )
        right_source = (
            pair_indices[left_index]
            if reverse_pairs and right_index < len(pair_indices)
            else pair_indices[right_index]
            if right_index < len(pair_indices)
            else None
        )
        left_page = src[left_source]
        right_page = src[right_source] if right_source is not None else None
        left_rect = left_page.rect
        right_rect = right_page.rect if right_page is not None else None
        width = left_rect.width + (right_rect.width if right_rect is not None else 0)
        height = max(left_rect.height, right_rect.height if right_rect is not None else left_rect.height)

        page = dst.new_page(width=width, height=height)
        page.show_pdf_page(fitz.Rect(0, 0, left_rect.width, left_rect.height), src, left_source)
        _ = (
            page.show_pdf_page(
                fitz.Rect(left_rect.width, 0, left_rect.width + right_rect.width, right_rect.height),
                src,
                right_source,
            )
            if right_page is not None and right_rect is not None
            else None
        )

    Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
    dst.save(dst_path)
    src.close()
    dst.close()
    used_pages = len(indices)
    paired_pages = len(pair_indices)
    dst_pages = head_count + (paired_pages + 1) // 2
    return SpreadStats(
        src_pages=src_page_count,
        used_pages=used_pages,
        dst_pages=dst_pages,
        head_single=head_count,
        paired=paired_pages // 2,
        single_tail=paired_pages % 2,
    )

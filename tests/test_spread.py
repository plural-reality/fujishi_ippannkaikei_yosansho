from __future__ import annotations

from pathlib import Path

from budget_cell.spread import build_spread_pdf


def test_build_spread_pdf(tmp_path: Path) -> None:
    import fitz

    src_path = tmp_path / "src.pdf"
    dst_path = tmp_path / "dst.pdf"

    src = fitz.open()
    src.new_page(width=100, height=200)
    src.new_page(width=100, height=200)
    src.new_page(width=100, height=200)
    src.save(src_path)
    src.close()

    stats = build_spread_pdf(str(src_path), str(dst_path))
    assert stats.src_pages == 3
    assert stats.used_pages == 3
    assert stats.dst_pages == 2
    assert stats.head_single == 0
    assert stats.paired == 1
    assert stats.single_tail == 1

    out = fitz.open(dst_path)
    assert out.page_count == 2
    assert round(out[0].rect.width) == 200
    assert round(out[0].rect.height) == 200
    assert round(out[1].rect.width) == 100
    assert round(out[1].rect.height) == 200
    out.close()


def test_build_spread_pdf_with_head_single(tmp_path: Path) -> None:
    import fitz

    src_path = tmp_path / "src_head.pdf"
    dst_path = tmp_path / "dst_head.pdf"

    src = fitz.open()
    src.new_page(width=100, height=200)
    src.new_page(width=100, height=200)
    src.new_page(width=100, height=200)
    src.new_page(width=100, height=200)
    src.save(src_path)
    src.close()

    stats = build_spread_pdf(str(src_path), str(dst_path), head_single_pages=1)
    assert stats.src_pages == 4
    assert stats.used_pages == 4
    assert stats.dst_pages == 3
    assert stats.head_single == 1
    assert stats.paired == 1
    assert stats.single_tail == 1

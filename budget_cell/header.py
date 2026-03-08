"""
Pure page header extraction: PageGeometry × Grid → PageHeader | None.

Extracts 款/項 metadata from Words above the table grid.
Independent of table parsing (parse.py). No IO.
"""

from __future__ import annotations

import re
from typing import Sequence

from budget_cell.types import Grid, PageGeometry, PageHeader, Word


# ---------------------------------------------------------------------------
# Pattern: full-width or half-width numeral + 款/項 + name
# ---------------------------------------------------------------------------

_KAN_RE = re.compile(r"([０-９\d]+)\s*款")
_KOU_RE = re.compile(r"([０-９\d]+)\s*項")


def _table_top(geom: PageGeometry, grid: Grid) -> float:
    """Determine the top edge of the table from horizontal lines or row boundaries."""
    h_ys = tuple(l.y0 for l in geom.lines if l.is_horizontal)
    return (
        min(grid.row_boundaries) if grid.row_boundaries
        else min(h_ys) if h_ys
        else 0.0
    )


def _words_above_grid(
    geom: PageGeometry,
    grid: Grid,
    margin: float = 5.0,
) -> tuple[Word, ...]:
    """Collect Words above the table's top boundary."""
    top = _table_top(geom, grid)
    cutoff = top - margin if top > margin else geom.height * 0.45
    return tuple(
        w for w in geom.words
        if w.y0 < cutoff
    )


def _normalize_text(value: str) -> str:
    return value.replace(" ", "").replace("\u3000", "")


def _extract_tagged(
    words: Sequence[Word],
    pattern: re.Pattern[str],
) -> tuple[str, str] | None:
    """Find 'N款/項 Name' pattern → (number, name) or None.

    The number is in the matching word, the name is the next word.
    """
    for i, w in enumerate(words):
        text = _normalize_text(w.text)
        m = pattern.search(text)
        if m is not None:
            number = m.group(1)
            # Name is the rest of this word after 款/項, or the next word
            suffix = text[m.end():].strip()
            name = (
                suffix if suffix
                else words[i + 1].text if i + 1 < len(words)
                else ""
            )
            return (number, name)

    for i, w in enumerate(words):
        joined = _normalize_text(
            f"{w.text}{words[i + 1].text if i + 1 < len(words) else ''}"
        )
        m = pattern.search(joined)
        if m is not None:
            number = m.group(1)
            suffix = joined[m.end():].strip()
            name = (
                suffix if suffix
                else words[i + 2].text if i + 2 < len(words)
                else ""
            )
            return (number, name)
    return None


def parse_page_header(
    geom: PageGeometry,
    grid: Grid,
) -> PageHeader | None:
    """Extract 款/項 from above-table Words. Returns None if not a budget data page."""
    above = _words_above_grid(geom, grid)
    sorted_above = tuple(sorted(above, key=lambda w: (w.y0, w.x0)))
    sorted_all = tuple(sorted(geom.words, key=lambda w: (w.y0, w.x0)))

    kan = _extract_tagged(sorted_above, _KAN_RE)
    kou = _extract_tagged(sorted_above, _KOU_RE)
    fallback_kan = _extract_tagged(sorted_all, _KAN_RE)
    fallback_kou = _extract_tagged(sorted_all, _KOU_RE)
    final_kan = kan if kan is not None else fallback_kan
    final_kou = kou if kou is not None else fallback_kou

    return (
        PageHeader(
            kan_number=final_kan[0],
            kan_name=final_kan[1],
            kou_number=final_kou[0],
            kou_name=final_kou[1],
        )
        if final_kan is not None and final_kou is not None
        else None
    )

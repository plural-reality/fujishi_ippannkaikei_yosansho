"""
Pure PageGeometry normalization.

Removes footer page-number artifacts before grid construction so layout
noise is not promoted into table rows.
"""

from __future__ import annotations

import re
from functools import reduce
from typing import Sequence

from budget_cell.types import PageGeometry, Word


_FOOTER_MIN_RATIO = 0.93
_LINE_Y_TOLERANCE = 3.0
_PAGE_NUMBER_LINE_RE = re.compile(r"^(?:-\d+-)+$")

_LineClusterAcc = tuple[tuple[tuple[Word, ...], ...], tuple[Word, ...], float | None]


def _normalized_text(words: Sequence[Word]) -> str:
    return "".join(word.text for word in words).replace(" ", "").replace("\u3000", "")


def _word_mid_y(word: Word) -> float:
    return (word.y0 + word.y1) / 2.0


def _line_cluster_step(acc: _LineClusterAcc, word: Word) -> _LineClusterAcc:
    lines, current_words, current_y = acc
    word_y = _word_mid_y(word)
    next_y = (
        word_y
        if current_y is None
        else (((current_y * len(current_words)) + word_y) / (len(current_words) + 1))
    )
    return (
        (lines, (*current_words, word), next_y)
        if current_words and current_y is not None and abs(word_y - current_y) <= _LINE_Y_TOLERANCE
        else ((*lines, tuple(current_words)), (word,), word_y)
        if current_words
        else (lines, (word,), word_y)
    )


def _finalize_line_clusters(acc: _LineClusterAcc) -> tuple[tuple[Word, ...], ...]:
    lines, current_words, _ = acc
    return (*lines, tuple(current_words)) if current_words else lines


def _cluster_words_into_lines(words: Sequence[Word]) -> tuple[tuple[Word, ...], ...]:
    sorted_words = tuple(sorted(words, key=lambda word: (_word_mid_y(word), word.x0)))
    return tuple(
        tuple(sorted(line, key=lambda word: word.x0))
        for line in _finalize_line_clusters(reduce(_line_cluster_step, sorted_words, ((), (), None)))
    )


def _footer_words(geom: PageGeometry) -> tuple[Word, ...]:
    cutoff = geom.height * _FOOTER_MIN_RATIO
    return tuple(word for word in geom.words if word.y0 >= cutoff)


def _page_number_lines(geom: PageGeometry) -> tuple[tuple[Word, ...], ...]:
    footer_lines = _cluster_words_into_lines(_footer_words(geom))
    return tuple(
        line
        for line in footer_lines
        if bool(_PAGE_NUMBER_LINE_RE.match(_normalized_text(line)))
    )


def normalize_page_geometry(geom: PageGeometry) -> PageGeometry:
    page_number_words = frozenset(
        word
        for line in _page_number_lines(geom)
        for word in line
    )
    return PageGeometry(
        width=geom.width,
        height=geom.height,
        lines=geom.lines,
        words=tuple(word for word in geom.words if word not in page_number_words),
    )


def normalize_page_geometries(geoms: Sequence[PageGeometry]) -> tuple[PageGeometry, ...]:
    return tuple(map(normalize_page_geometry, geoms))

"""
Pluggable key matchers for trend aggregation.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable

from budget_cell.trend import TrendKey


MatchIdFn = Callable[[TrendKey], str]

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[・･/／\\,，、\-−ー―()（）「」『』【】［］\[\]：:;；]")
_VARIANT_MAP = str.maketrans({
    "ヶ": "ケ",
    "ヵ": "ケ",
    "ケ": "ケ",
})


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).upper()
    no_space = _SPACE_RE.sub("", normalized)
    no_punct = _PUNCT_RE.sub("", no_space)
    return no_punct.translate(_VARIANT_MAP)


def trend_key_match_id_strict(key: TrendKey) -> str:
    return "|".join((key.kan_name, key.kou_name, key.moku_name, *key.path_levels))


def trend_key_match_id_loose(key: TrendKey) -> str:
    return "|".join(
        (
            _normalize_token(key.kan_name),
            _normalize_token(key.kou_name),
            _normalize_token(key.moku_name),
            *tuple(_normalize_token(level) for level in key.path_levels),
        )
    )


MATCHERS: dict[str, MatchIdFn] = {
    "strict": trend_key_match_id_strict,
    "loose": trend_key_match_id_loose,
}

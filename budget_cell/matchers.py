"""
Pluggable key matchers for comparison aggregation.
"""

from __future__ import annotations

import re
import unicodedata

from budget_cell.comparison import MatchIdFn, ComparisonKey, comparison_key_match_id_strict

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


def comparison_key_match_id_loose(key: ComparisonKey) -> str:
    return "|".join(
        (
            _normalize_token(key.kan_name),
            _normalize_token(key.kou_name),
            _normalize_token(key.moku_name),
            _normalize_token(key.node_kind),
            *tuple(_normalize_token(level) for level in key.path_levels),
        )
    )


MATCHERS: dict[str, MatchIdFn] = {
    "strict": comparison_key_match_id_strict,
    "loose": comparison_key_match_id_loose,
}

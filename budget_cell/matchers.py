"""
Pluggable key matchers for trend aggregation.

Matchers are composable via pipelines of transform functions.
Each transform is a simple str -> str function.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, Sequence

from budget_cell.trend import MatchIdFn, TrendKey, trend_key_match_id_strict

# ---------------------------------------------------------------------------
# Transform functions (str -> str)
# ---------------------------------------------------------------------------

TokenTransform = Callable[[str], str]

_SPACE_RE = re.compile(r"[\s\u3000]+")
_PUNCT_RE = re.compile(r"[・･/／\\,，、\-−ー―()（）「」『』【】［］\[\]：:;；]")
_VARIANT_MAP = str.maketrans({
    "ヶ": "ケ",
    "ヵ": "ケ",
    "ケ": "ケ",
})


def nfkc(value: str) -> str:
    """NFKC正規化: 全角数字→半角、合字分解など."""
    return unicodedata.normalize("NFKC", value)


def upper(value: str) -> str:
    """大文字化."""
    return value.upper()


def remove_space(value: str) -> str:
    """全てのスペース（半角・全角）を削除."""
    return _SPACE_RE.sub("", value)


def remove_punct(value: str) -> str:
    """句読点・括弧・記号を削除."""
    return _PUNCT_RE.sub("", value)


def unify_ke(value: str) -> str:
    """促音便ケの統一: ヶ, ヵ → ケ."""
    return value.translate(_VARIANT_MAP)


# ---------------------------------------------------------------------------
# Pipeline composition
# ---------------------------------------------------------------------------

def compose(*transforms: TokenTransform) -> TokenTransform:
    """複数の変換関数を合成して1つの変換関数にする."""
    def composed(value: str) -> str:
        result = value
        for transform in transforms:
            result = transform(result)
        return result
    return composed


def make_matcher(transforms: Sequence[TokenTransform]) -> MatchIdFn:
    """変換関数のリストからマッチャーを生成する.

    Args:
        transforms: 適用する変換関数のリスト（順番に適用される）

    Returns:
        TrendKey を受け取り match_id 文字列を返す関数
    """
    transform = compose(*transforms) if transforms else (lambda x: x)

    def match_id_fn(key: TrendKey) -> str:
        return "|".join(
            (
                transform(key.kan_name),
                transform(key.kou_name),
                transform(key.moku_name),
                *tuple(transform(level) for level in key.path_levels),
            )
        )
    return match_id_fn


# ---------------------------------------------------------------------------
# Preset pipelines
# ---------------------------------------------------------------------------

# Loose: 従来の緩いマッチング（表記ゆれを統一）
LOOSE_TRANSFORMS: tuple[TokenTransform, ...] = (
    nfkc,
    upper,
    remove_space,
    remove_punct,
    unify_ke,
)

# 日本語向け: スペースと句読点の正規化のみ（大文字化なし）
JAPANESE_TRANSFORMS: tuple[TokenTransform, ...] = (
    nfkc,
    remove_space,
    remove_punct,
    unify_ke,
)

# シンプル: NFKCとスペース削除のみ
SIMPLE_TRANSFORMS: tuple[TokenTransform, ...] = (
    nfkc,
    remove_space,
)


def trend_key_match_id_loose(key: TrendKey) -> str:
    """従来互換: 緩いマッチング."""
    return make_matcher(LOOSE_TRANSFORMS)(key)


def trend_key_match_id_japanese(key: TrendKey) -> str:
    """日本語向けマッチング（大文字化なし）."""
    return make_matcher(JAPANESE_TRANSFORMS)(key)


def trend_key_match_id_simple(key: TrendKey) -> str:
    """シンプルなマッチング（NFKCとスペース削除のみ）."""
    return make_matcher(SIMPLE_TRANSFORMS)(key)


# ---------------------------------------------------------------------------
# Matcher registry
# ---------------------------------------------------------------------------

MATCHERS: dict[str, MatchIdFn] = {
    "strict": trend_key_match_id_strict,
    "loose": trend_key_match_id_loose,
    "japanese": trend_key_match_id_japanese,
    "simple": trend_key_match_id_simple,
}

# 変換関数のレジストリ（名前でアクセス可能に）
TRANSFORMS: dict[str, TokenTransform] = {
    "nfkc": nfkc,
    "upper": upper,
    "remove_space": remove_space,
    "remove_punct": remove_punct,
    "unify_ke": unify_ke,
}


def get_matcher(name: str) -> MatchIdFn:
    """名前からマッチャーを取得."""
    if name not in MATCHERS:
        raise ValueError(f"Unknown matcher: {name}. Available: {list(MATCHERS.keys())}")
    return MATCHERS[name]


def get_transforms(names: Sequence[str]) -> tuple[TokenTransform, ...]:
    """名前のリストから変換関数のタプルを取得."""
    result = []
    for name in names:
        if name not in TRANSFORMS:
            raise ValueError(f"Unknown transform: {name}. Available: {list(TRANSFORMS.keys())}")
        result.append(TRANSFORMS[name])
    return tuple(result)

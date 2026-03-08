"""
Domain types — Single Source of Truth for all immutable data structures.

All types are frozen dataclasses. No logic, no IO, no dependencies beyond stdlib.
This module is the leaf of the dependency graph — everything else depends on it.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# PDF geometry types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Line:
    x0: float
    y0: float
    x1: float
    y1: float
    linewidth: float

    @property
    def is_vertical(self) -> bool:
        return abs(self.x1 - self.x0) < 1.0

    @property
    def is_horizontal(self) -> bool:
        return abs(self.y1 - self.y0) < 1.0


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class PageGeometry:
    width: float
    height: float
    lines: tuple[Line, ...]
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Grid:
    col_boundaries: tuple[float, ...]   # sorted X positions
    row_boundaries: tuple[float, ...]   # sorted Y positions


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    words: tuple[Word, ...]  # original Words, sorted by x0


# ---------------------------------------------------------------------------
# Page header types (above-table metadata)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PageHeader:
    """款/項 metadata extracted from above-table words."""
    kan_number: str    # Full-width numeral ("１", "２", ...)
    kan_name: str      # "議会費", "総務費", ...
    kou_number: str
    kou_name: str


# ---------------------------------------------------------------------------
# Budget domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetsumeiEntry:
    """Parsed entry from the 説明 column."""
    kind: str        # "coded" (3-digit code) | "text"
    code: str | None
    name: str
    amount: int | None
    supplement: str = ""


@dataclass(frozen=True)
class Zaigen:
    """財源内訳 (immutable record)."""
    kokuken: int | None    # 国県支出金
    chihousei: int | None  # 地方債
    sonota: int | None     # その他
    ippan: int | None      # 一般財源


@dataclass(frozen=True)
class SetsuRecord:
    """節レコード."""
    number: int | None
    name: str
    amount: int | None
    sub_items: tuple[tuple[str, int | None], ...]  # 小区分 (name, amount)
    setsumei: tuple[SetsumeiEntry, ...]


@dataclass(frozen=True)
class MokuRecord:
    """目レコード."""
    name: str
    honendo: int | None
    zenendo: int | None
    hikaku: int | None
    zaigen: Zaigen
    setsu_list: tuple[SetsuRecord, ...]


@dataclass(frozen=True)
class PageBudget:
    """1ページ分の構造化予算データ."""
    moku_records: tuple[MokuRecord, ...]
    orphan_setsu: tuple[SetsuRecord, ...]  # 目が前ページにある右表行


# ---------------------------------------------------------------------------
# Flatten output type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlatRow:
    """Non-normalized single row — carries full context from 款 to 説明."""
    kan_name: str
    kou_name: str
    moku_name: str
    honendo: int | None
    zenendo: int | None
    hikaku: int | None
    kokuken: int | None
    chihousei: int | None
    sonota: int | None
    ippan: int | None
    setsu_number: int | None
    setsu_name: str
    setsu_amount: int | None
    sub_item_name: str
    sub_item_amount: int | None
    setsumei_code: str
    setsumei_name: str
    setsumei_supplement: str
    setsumei_amount: int | None

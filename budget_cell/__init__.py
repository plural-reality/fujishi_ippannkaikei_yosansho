"""
budget_cell — PDF budget table extraction pipeline.

Architecture:
  types.py    ← all domain types (SSOT, no dependencies)
  extract.py  ← IO boundary: pdfplumber → PageGeometry
  grid.py     ← pure: PageGeometry → Grid
  cells.py    ← pure: PageGeometry × Grid → Cell[]
  parse.py    ← pure: Cell[] → PageBudget
  flatten.py  ← pure: PageBudget → FlatRow[]
  overlay.py  ← IO boundary: fitz rendering
"""

from budget_cell.types import (
    Cell,
    FlatRow,
    Grid,
    Line,
    MokuRecord,
    PageBudget,
    PageGeometry,
    SetsuRecord,
    SetsumeiEntry,
    Word,
    Zaigen,
)

__all__ = [
    "Cell", "FlatRow", "Grid", "Line",
    "MokuRecord", "PageBudget", "PageGeometry",
    "SetsuRecord", "SetsumeiEntry", "Word", "Zaigen",
]

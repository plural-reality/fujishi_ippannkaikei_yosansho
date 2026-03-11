from __future__ import annotations

from budget_cell.geometry_normalize import normalize_page_geometry
from budget_cell.grid import build_grid
from budget_cell.types import PageGeometry, Word


def _sample_geom() -> PageGeometry:
    return PageGeometry(
        width=1200.0,
        height=842.0,
        lines=(),
        words=(
            Word(x0=60.0, y0=740.0, x1=120.0, y1=752.0, text="説明"),
            Word(x0=260.0, y0=740.0, x1=320.0, y1=752.0, text="100"),
            Word(x0=280.0, y0=804.6, x1=288.0, y1=814.0, text="-"),
            Word(x0=294.0, y0=804.6, x1=316.0, y1=814.0, text="240"),
            Word(x0=320.0, y0=804.6, x1=328.0, y1=814.0, text="-"),
            Word(x0=880.0, y0=804.6, x1=888.0, y1=814.0, text="-"),
            Word(x0=894.0, y0=804.6, x1=916.0, y1=814.0, text="241"),
            Word(x0=920.0, y0=804.6, x1=928.0, y1=814.0, text="-"),
        ),
    )


def test_normalize_page_geometry_removes_footer_page_number_words() -> None:
    geom = _sample_geom()

    normalized = normalize_page_geometry(geom)

    assert tuple(word.text for word in normalized.words) == ("説明", "100")


def test_normalize_page_geometry_runs_before_grid_row_clustering() -> None:
    geom = _sample_geom()

    raw_grid = build_grid(geom)
    normalized_grid = build_grid(normalize_page_geometry(geom))

    assert 804.6 in raw_grid.row_boundaries
    assert 804.6 not in normalized_grid.row_boundaries

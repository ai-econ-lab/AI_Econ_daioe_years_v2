"""Data loading, lazy frame, and data-derived input constants."""

from pathlib import Path

import polars as pl

from .constants import AGE_ORDER

BASE_DIR = Path(__file__).resolve().parent.parent

INTRO_MD: str = (BASE_DIR / "md_files" / "intro.md").read_text(encoding="utf-8")

_ABOUT_TEMPLATE: str = (BASE_DIR / "md_files" / "about.md").read_text(encoding="utf-8")

DATA_PATH = BASE_DIR / "data" / "daioe_scb_years_processed.parquet"

lf = pl.scan_parquet(DATA_PATH)
lf.collect_schema()

LEVELS: list[str] = (
    lf.select(pl.col("level").unique().sort()).collect().to_series().to_list()
)

SEXES: list[str] = (
    lf.select(pl.col("sex").unique().sort()).collect().to_series().to_list()
)

_present = lf.select(pl.col("age_group").unique()).collect().to_series().to_list()
AGES: list[str] = [x for x in AGE_ORDER if x in _present]

YEARS: list[int] = (
    lf.select(pl.col("year").unique().sort()).collect().to_series().to_list()
)

YEAR_MIN: int = min(YEARS)
YEAR_MAX: int = max(YEARS)

ABOUT_MD: str = _ABOUT_TEMPLATE.format(YEAR_MIN=YEAR_MIN, YEAR_MAX=YEAR_MAX)


def build_choices_by_level(
    lf: pl.LazyFrame,
    levels: list[str],
) -> dict[str, dict[str, str]]:
    """Return a dict mapping each SSYK level to its sorted occupation choices."""
    out: dict[str, dict[str, str]] = {}
    for lvl in levels:
        occs = (
            lf.filter(pl.col("level") == lvl)
            .select(pl.col("occupation").unique().sort())
            .collect()
            .to_series()
            .to_list()
        )
        out[lvl] = {o: o for o in occs}
    return out

"""Data loading, lazy frame, and data-derived input constants."""

from pathlib import Path

import polars as pl

from .constants import AGE_ORDER

BASE_DIR = Path(__file__).resolve().parent.parent

INTRO_MD: str = (BASE_DIR / "md_files" / "intro.md").read_text(encoding="utf-8")

_ABOUT_TEMPLATE: str = (BASE_DIR / "md_files" / "about.md").read_text(encoding="utf-8")

DATA_PATH = BASE_DIR / "data" / "daioe_scb_years_processed.parquet"

lf = pl.read_parquet(DATA_PATH).lazy()
lf.collect_schema()

# Query metadata in parallel using collect_all
lf_levels = lf.select(pl.col("level").unique().sort())
lf_sexes = lf.select(pl.col("sex").unique().sort())
lf_ages = lf.select(pl.col("age_group").unique())
lf_years = lf.select(pl.col("year").unique().sort())

_meta_dfs = pl.collect_all([lf_levels, lf_sexes, lf_ages, lf_years])

LEVELS: list[str] = _meta_dfs[0].to_series().to_list()
SEXES: list[str] = _meta_dfs[1].to_series().to_list()
_present = _meta_dfs[2].to_series().to_list()
AGES: list[str] = [x for x in AGE_ORDER if x in _present]
YEARS: list[int] = _meta_dfs[3].to_series().to_list()

YEAR_MIN: int = min(YEARS)
YEAR_MAX: int = max(YEARS)

ABOUT_MD: str = _ABOUT_TEMPLATE.format(YEAR_MIN=YEAR_MIN, YEAR_MAX=YEAR_MAX)


def build_choices_by_level(
    lf: pl.LazyFrame,
    levels: list[str],
) -> dict[str, dict[str, str]]:
    """Return a dict mapping each SSYK level to its sorted occupation choices."""
    # Retrieve all unique level-occupation pairs in a single collect
    df_occs = (
        lf.select(["level", "occupation"])
        .unique()
        .sort(["level", "occupation"])
        .collect()
    )
    out: dict[str, dict[str, str]] = {}
    for lvl in levels:
        occs = (
            df_occs.filter(pl.col("level") == lvl)
            .select("occupation")
            .to_series()
            .to_list()
        )
        out[lvl] = {o: o for o in occs}
    return out

import polars as pl

from .constants import (
    AI_LABELS,
    AI_LEVEL_COLS,
    AI_PCTL_COLS,
    AI_WAVG_COLS,
    EXPOSURE_LABELS,
)


def get_occ_summary(lf: pl.LazyFrame, occupation: str, year: int) -> dict | None:
    """
    Aggregate employment count and percentage changes for one occupation and year.

    Returns a dict with keys: employment, pct_1y, pct_3y, pct_5y, year.
    Returns None if no data matches the filters.
    """
    df = (
        lf.filter(
            (pl.col("occupation") == occupation) & (pl.col("year") == year),
        )
        .select(["count", "pct_chg_1y", "pct_chg_3y", "pct_chg_5y", "year"])
        .collect()
    )

    if df.is_empty():
        return None

    def _mean_or_none(col: str) -> float | None:
        val = df[col].mean()
        return None if val is None else float(val)

    return {
        "employment": df["count"].sum(),
        "pct_1y": _mean_or_none("pct_chg_1y"),
        "pct_3y": _mean_or_none("pct_chg_3y"),
        "pct_5y": _mean_or_none("pct_chg_5y"),
        "year": int(df["year"][0]),
    }


def get_occ_ai_exposure(
    lf: pl.LazyFrame,
    occupation: str,
    year: int,
) -> pl.DataFrame:
    """
    Return mean weighted AI exposure scores, exposure levels, and percentile ranks per sub-domain.

    Returns a long-format DataFrame with columns: domain, score, level, level_label, percentile.
    Used to power the ranked horizontal bar chart in Card 2.
    """
    select_cols = AI_WAVG_COLS + AI_LEVEL_COLS + AI_PCTL_COLS
    df = (
        lf.filter(
            (pl.col("occupation") == occupation) & (pl.col("year") == year),
        )
        .select(select_cols)
        .collect()
    )

    rows = []
    for wavg_col, level_col, pctl_col in zip(
        AI_WAVG_COLS,
        AI_LEVEL_COLS,
        AI_PCTL_COLS,
        strict=False,
    ):
        raw_level = df[level_col].mean()
        level_val = round(raw_level) if raw_level is not None else None
        rows.append(
            {
                "domain": AI_LABELS[wavg_col],
                "score": df[wavg_col].mean(),
                "level": level_val,
                "level_label": EXPOSURE_LABELS.get(level_val, "Unknown")
                if level_val
                else "Unknown",
                "percentile": df[pctl_col].mean(),
            },
        )
    return pl.DataFrame(rows).sort("score")


def get_occ_ai_trend(
    lf: pl.LazyFrame,
    occupation: str,
    year_range: tuple[int, int],
) -> pl.DataFrame:
    """
    Return yearly mean weighted AI exposure (All Applications) for one occupation over a year range.

    Returns a DataFrame with columns: year, daioe_allapps_wavg.
    """
    year_min, year_max = year_range
    return (
        lf.filter(
            (pl.col("occupation") == occupation)
            & (pl.col("year") >= year_min)
            & (pl.col("year") <= year_max),
        )
        .group_by("year")
        .agg(pl.col("daioe_allapps_wavg").mean())
        .sort("year")
        .collect()
    )


def get_comparison_employment(
    lf: pl.LazyFrame,
    occupations: list[str],
    age_groups: list[str],
) -> pl.DataFrame:
    """
    Return total employment per year/occupation for the comparison view.

    Aggregates across all sexes and the selected age groups.
    Returns a DataFrame with columns: year, occupation, count.
    """
    return (
        lf.filter(
            pl.col("occupation").is_in(occupations)
            & pl.col("age_group").is_in(age_groups),
        )
        .group_by(["year", "occupation"])
        .agg(
            [
                pl.col("count").sum(),
                pl.col("pct_chg_1y").mean(),
            ],
        )
        .sort(["occupation", "year"])
        .collect()
    )


def get_comp_radar(
    lf: pl.LazyFrame,
    occupations: list[str],
    year: int,
) -> pl.DataFrame:
    """
    Return mean AI percentile scores per occupation for the radar chart.

    Returns a DataFrame with columns: occupation, pctl_<metric>_wavg for each metric.
    """
    return (
        lf.filter(
            pl.col("occupation").is_in(occupations) & (pl.col("year") == year),
        )
        .group_by("occupation")
        .agg([pl.col(c).mean() for c in AI_PCTL_COLS])
        .collect()
    )


def get_occ_employment_by_age(
    lf: pl.LazyFrame,
    occupation: str,
    year_range: tuple[int, int],
    age_groups: list[str],
) -> pl.DataFrame:
    """
    Return yearly employment counts per age group for a given occupation and year range.

    Returns a long-format DataFrame with columns: year, age_group, count.
    """
    year_min, year_max = year_range
    return (
        lf.filter(
            (pl.col("occupation") == occupation)
            & (pl.col("year") >= year_min)
            & (pl.col("year") <= year_max)
            & (pl.col("age_group").is_in(age_groups)),
        )
        .group_by(["year", "age_group"])
        .agg(
            [
                pl.col("count").sum(),
                pl.col("pct_chg_1y").mean(),
            ],
        )
        .sort(["age_group", "year"])
        .collect()
    )

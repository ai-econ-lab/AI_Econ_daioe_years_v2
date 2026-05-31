import polars as pl

from .constants import (
    AI_LABELS,
    AI_LEVEL_COLS,
    AI_PCTL_COLS,
    AI_WAVG_COLS,
    EXPOSURE_LABELS,
)


def _null_safe_sum(col: str) -> pl.Expr:
    """Sum a change column, returning null (not 0) when every value in the group is null."""
    return (
        pl.when(pl.col(col).is_null().all())
        .then(pl.lit(None, dtype=pl.Float64))
        .otherwise(pl.col(col).sum())
        .alias(col)
    )


def _safe_pct(chg_col: str, emp_col: str, alias: str) -> pl.Expr:
    """Derive pct change from aggregated totals: chg / prev_emp * 100, null-safe."""
    prev = pl.col(emp_col) - pl.col(chg_col)
    return (
        pl.when(pl.col(chg_col).is_not_null() & (prev != 0))
        .then(pl.col(chg_col) / prev * 100)
        .otherwise(None)
        .alias(alias)
    )


def _pairs_filter(
    lf: pl.LazyFrame,
    occ_pairs: list[tuple[str, str]],
) -> pl.LazyFrame:
    """Filter LazyFrame to rows matching the (level, occupation) pairs via a join."""
    if not occ_pairs:
        return lf.filter(pl.lit(False))
    keys = pl.DataFrame(
        {
            "level": [p[0] for p in occ_pairs],
            "occupation": [p[1] for p in occ_pairs],
        }
    ).lazy()
    return lf.join(keys, on=["level", "occupation"], how="inner")


def get_occ_summary(
    lf: pl.LazyFrame,
    level: str,
    occupation: str,
    year: int,
) -> dict | None:
    """
    Aggregate employment count and percentage changes for one occupation and year.

    Filters by both level and occupation to avoid double-counting occupations that
    share a name across SSYK levels.
    Returns a dict with keys: employment, pct_1y, pct_3y, pct_5y, year.
    Returns None if no data matches the filters.
    """
    df = (
        lf.filter(
            (pl.col("level") == level)
            & (pl.col("occupation") == occupation)
            & (pl.col("year") == year),
        )
        .group_by("occupation")
        .agg(
            [
                pl.col("count").sum(),
                _null_safe_sum("chg_1y"),
                _null_safe_sum("chg_3y"),
                _null_safe_sum("chg_5y"),
                pl.col("year").first(),
            ],
        )
        .with_columns(
            [
                _safe_pct("chg_1y", "count", "pct_chg_1y"),
                _safe_pct("chg_3y", "count", "pct_chg_3y"),
                _safe_pct("chg_5y", "count", "pct_chg_5y"),
            ],
        )
        .collect()
    )

    if df.is_empty():
        return None

    row = df.row(0, named=True)
    return {
        "employment": row["count"],
        "pct_1y": row["pct_chg_1y"],
        "pct_3y": row["pct_chg_3y"],
        "pct_5y": row["pct_chg_5y"],
        "year": int(row["year"]),
    }


def get_occ_ai_exposure(
    lf: pl.LazyFrame,
    level: str,
    occupation: str,
    year: int,
) -> pl.DataFrame:
    """
    Return mean weighted AI exposure scores, exposure levels, and percentile ranks per sub-domain.

    Filters by level and occupation to avoid aggregating across SSYK levels.
    Returns a long-format DataFrame with columns: domain, score, level, level_label, percentile.
    """
    select_cols = AI_WAVG_COLS + AI_LEVEL_COLS + AI_PCTL_COLS
    df = (
        lf.filter(
            (pl.col("level") == level)
            & (pl.col("occupation") == occupation)
            & (pl.col("year") == year),
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


def get_occ_employment_by_age(
    lf: pl.LazyFrame,
    level: str,
    occupation: str,
    year_range: tuple[int, int],
    age_groups: list[str],
    extra_sexes: tuple[str, ...] = (),
) -> pl.DataFrame:
    """
    Return yearly employment counts per age group for a given occupation and year range.

    Filters by level and occupation to avoid cross-level aggregation.
    Always includes an "All" series (all sexes aggregated). Pass extra_sexes to overlay
    individual sex breakdowns (e.g. ("men", "women")).
    Returns a DataFrame with columns: year, age_group, count, chg_1y, pct_chg_1y, sex, series.
    """
    year_min, year_max = year_range
    base = lf.filter(
        (pl.col("level") == level)
        & (pl.col("occupation") == occupation)
        & (pl.col("age_group").is_in(age_groups)),
    )

    def _by_age(lf_in: pl.LazyFrame, sex_label: str) -> pl.DataFrame:
        return (
            lf_in.group_by(["year", "age_group"])
            .agg([pl.col("count").sum(), _null_safe_sum("chg_1y")])
            .with_columns(_safe_pct("chg_1y", "count", "pct_chg_1y"))
            .filter(pl.col("year").is_between(year_min, year_max))
            .with_columns(pl.lit(sex_label).alias("sex"))
            .sort(["age_group", "year"])
            .collect()
        )

    frames = [_by_age(base, "All")]
    for s in extra_sexes:
        frames.append(_by_age(base.filter(pl.col("sex") == s), s.capitalize()))

    df = pl.concat(frames)
    if extra_sexes:
        return df.with_columns(
            (pl.col("age_group") + " (" + pl.col("sex") + ")").alias("series")
        )
    return df.with_columns(pl.col("age_group").alias("series"))


def get_comparison_employment(
    lf: pl.LazyFrame,
    occ_pairs: list[tuple[str, str]],
    age_groups: list[str],
) -> pl.DataFrame:
    """
    Return total employment per year for each (level, occupation) pair.

    occ_pairs: list of (level, occupation) tuples identifying each selected occupation.
    Aggregates across all sexes and the selected age groups.
    Returns a DataFrame with columns: year, level, occupation, count, pct_chg_1y.
    """
    return (
        _pairs_filter(lf, occ_pairs)
        .filter(pl.col("age_group").is_in(age_groups))
        .group_by(["year", "level", "occupation"])
        .agg(
            [
                pl.col("count").sum(),
                _null_safe_sum("chg_1y"),
            ],
        )
        .with_columns(
            _safe_pct("chg_1y", "count", "pct_chg_1y"),
        )
        .sort(["level", "occupation", "year"])
        .collect()
    )


def get_comp_summary(
    lf: pl.LazyFrame,
    occ_pairs: list[tuple[str, str]],
    year: int,
    age_groups: list[str],
) -> pl.DataFrame:
    """
    Return a per-occupation employment summary for the selected year and age groups.

    occ_pairs: list of (level, occupation) tuples.
    Returns a DataFrame with columns: level, occupation, count, pct_chg_1y, pct_chg_3y, pct_chg_5y.
    """
    return (
        _pairs_filter(lf, occ_pairs)
        .filter(
            (pl.col("year") == year) & pl.col("age_group").is_in(age_groups),
        )
        .group_by(["level", "occupation"])
        .agg(
            [
                pl.col("count").sum(),
                _null_safe_sum("chg_1y"),
                _null_safe_sum("chg_3y"),
                _null_safe_sum("chg_5y"),
            ],
        )
        .with_columns(
            [
                _safe_pct("chg_1y", "count", "pct_chg_1y"),
                _safe_pct("chg_3y", "count", "pct_chg_3y"),
                _safe_pct("chg_5y", "count", "pct_chg_5y"),
            ],
        )
        .sort(["level", "occupation"])
        .collect()
    )


def get_all_occ_summary(lf: pl.LazyFrame, level: str, year: int) -> pl.DataFrame:
    """
    Return yearly employment summary for every occupation at the given SSYK level and year.

    Aggregates across all sexes and age groups; derives pct changes from aggregated totals.
    Returns a DataFrame with columns: occupation, count, pct_chg_1y, pct_chg_3y, pct_chg_5y.
    """
    return (
        lf.filter(
            (pl.col("level") == level) & (pl.col("year") == year),
        )
        .group_by("occupation")
        .agg(
            [
                pl.col("count").sum(),
                _null_safe_sum("chg_1y"),
                _null_safe_sum("chg_3y"),
                _null_safe_sum("chg_5y"),
            ],
        )
        .with_columns(
            [
                _safe_pct("chg_1y", "count", "pct_chg_1y"),
                _safe_pct("chg_3y", "count", "pct_chg_3y"),
                _safe_pct("chg_5y", "count", "pct_chg_5y"),
            ],
        )
        .sort("occupation")
        .collect()
    )


def get_all_occ_ai_exposure(lf: pl.LazyFrame, level: str, year: int) -> pl.DataFrame:
    """
    Return AI percentile scores for every occupation at the given SSYK level, long format.

    Returns a DataFrame with columns: occupation, domain, percentile.
    Sorted by occupation ascending, percentile descending within each occupation.
    """
    label_map = {col: AI_LABELS[col[5:]] for col in AI_PCTL_COLS}
    wide_df = (
        lf.filter(
            (pl.col("level") == level) & (pl.col("year") == year),
        )
        .group_by("occupation")
        .agg([pl.col(c).mean() for c in AI_PCTL_COLS])
        .collect()
    )
    return (
        wide_df.unpivot(
            on=AI_PCTL_COLS,
            index="occupation",
            variable_name="pctl_col",
            value_name="percentile",
        )
        .with_columns(
            pl.col("pctl_col")
            .replace(old=list(label_map.keys()), new=list(label_map.values()))
            .alias("domain"),
        )
        .drop("pctl_col")
        .sort(["occupation", "percentile"], descending=[False, True])
    )


def get_comp_radar(
    lf: pl.LazyFrame,
    occ_pairs: list[tuple[str, str]],
    year: int,
) -> pl.DataFrame:
    """
    Return mean AI percentile scores per (level, occupation) pair for the radar chart.

    Returns a DataFrame with columns: level, occupation, pctl_<metric>_wavg for each metric.
    """
    return (
        _pairs_filter(lf, occ_pairs)
        .filter(pl.col("year") == year)
        .group_by(["level", "occupation"])
        .agg([pl.col(c).mean() for c in AI_PCTL_COLS])
        .collect()
    )

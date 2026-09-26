"""
validate.py.
------------
Gate for the yearly dataset the app deploys and publishes. Runs in
03_development_to_main.yml before anything is promoted to `main` or released,
and exits non-zero listing every failed check.

Usage:
    python scripts/validate.py data/daioe_scb_years_processed.parquet
    python scripts/validate.py NEW.parquet --previous DEPLOYED.parquet
"""

import argparse
import sys
from pathlib import Path

import polars as pl
import polars.selectors as cs

KEY = ["year", "level", "ssyk_code", "age", "sex"]
EXPECTED_LEVELS = {"SSYK1", "SSYK2", "SSYK3", "SSYK4"}
EXPECTED_SEXES = {"men", "women"}
EXPECTED_AGES = 10
EXPECTED_SSYK1_CODES = {str(i) for i in range(1, 10)}
FIRST_YEAR = 2014

# Plausibility bounds for the national total (persons, summed over the nine
# SSYK1 groups, all ages and both sexes). The series runs from about 3.9 to
# 5.0 million; a doubled or halved total falls outside.
TOTAL_EMPLOYMENT_BOUNDS = (3_000_000, 7_000_000)

# The military is excluded, so every SSYK1 group has a DAIOE score. A missing
# one means unscored occupations are propagating again.
GUARD_METRIC = "daioe_allapps_wavg"


def check_structure(df: pl.DataFrame) -> list[str]:
    """Check keys, dimensions and year coverage."""
    required = [*KEY, "occupation", "count", GUARD_METRIC]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [f"missing required columns: {missing}"]

    failures = []
    duplicates = df.height - df.select(KEY).unique().height
    if duplicates:
        failures.append(f"{duplicates} duplicate rows on key {KEY}")

    levels = set(df["level"].unique())
    if levels != EXPECTED_LEVELS:
        failures.append(
            f"levels are {sorted(levels)}, expected {sorted(EXPECTED_LEVELS)}"
        )

    sexes = set(df["sex"].unique())
    if sexes != EXPECTED_SEXES:
        failures.append(f"sexes are {sorted(sexes)}, expected {sorted(EXPECTED_SEXES)}")

    ages = df["age"].n_unique()
    if ages != EXPECTED_AGES:
        failures.append(f"{ages} age bands, expected {EXPECTED_AGES}")

    codes = set(df.filter(pl.col("level") == "SSYK1")["ssyk_code"].unique())
    if codes != EXPECTED_SSYK1_CODES:
        failures.append(f"SSYK1 codes are {sorted(codes)}, expected 1-9")

    years = sorted(df["year"].unique())
    if years != list(range(years[0], years[-1] + 1)):
        failures.append(f"years are not contiguous: {years}")
    if years[0] != FIRST_YEAR:
        failures.append(f"first year is {years[0]}, expected {FIRST_YEAR}")

    if df.group_by("year").agg(pl.len())["len"].n_unique() != 1:
        failures.append("years do not all have the same number of rows")
    return failures


def check_values(df: pl.DataFrame) -> list[str]:
    """Check for NaN/inf, range violations and the exposure null pattern."""
    failures = []

    for column in df.select(cs.float()).columns:
        bad = df.select(
            (pl.col(column).is_nan() | pl.col(column).is_infinite()).sum(),
        ).item()
        if bad:
            failures.append(f"{column}: {bad} NaN/inf values")

    if df["count"].null_count():
        failures.append(f"count: {df['count'].null_count()} null values")
    if (df["count"] < 0).any():
        failures.append("count has negative values")

    low, high = TOTAL_EMPLOYMENT_BOUNDS
    totals = (
        df.filter(pl.col("level") == "SSYK1")
        .group_by("year")
        .agg(pl.col("count").sum().alias("total"))
    )
    outside = totals.filter((pl.col("total") < low) | (pl.col("total") > high))
    if outside.height:
        worst = outside.sort("total")["total"].to_list()
        failures.append(
            f"{outside.height} years have a national total outside {low:,}-{high:,} "
            f"(range {worst[0]:,}-{worst[-1]:,})",
        )

    for column in df.select(cs.starts_with("pctl_")).columns:
        lo, hi = df[column].min(), df[column].max()
        if lo is not None and not (0 <= lo and hi <= 100):
            failures.append(f"{column}: outside 0-100 (min {lo}, max {hi})")

    for column in df.select(cs.ends_with("_Level_Exposure")).columns:
        lo, hi = df[column].min(), df[column].max()
        if lo is not None and not (1 <= lo and hi <= 5):
            failures.append(f"{column}: outside 1-5 (min {lo}, max {hi})")

    # A percentile and level exist exactly when the score does. A percentile
    # on a null score is how unscored occupations got ranked as most exposed.
    for wavg in df.select(cs.ends_with("_wavg") & cs.starts_with("daioe_")).columns:
        metric = wavg[len("daioe_") : -len("_wavg")]
        for derived in (f"pctl_daioe_{metric}_wavg", f"daioe_{metric}_Level_Exposure"):
            if derived not in df.columns:
                continue
            mismatch = df.select(
                (pl.col(wavg).is_null() != pl.col(derived).is_null()).sum(),
            ).item()
            if mismatch:
                failures.append(
                    f"{derived}: null pattern differs from {wavg} in {mismatch} rows",
                )

    unscored = df.filter(pl.col("level") == "SSYK1")[GUARD_METRIC].null_count()
    if unscored:
        failures.append(f"{GUARD_METRIC}: {unscored} SSYK1 rows have no score")

    return failures


def check_against_previous(df: pl.DataFrame, previous: pl.DataFrame) -> list[str]:
    """Check the new dataset has not shrunk or lost columns or years."""
    failures = []

    lost = sorted(set(previous.columns) - set(df.columns))
    if lost:
        failures.append(f"columns missing versus the deployed data: {lost}")
    if df.height < previous.height:
        failures.append(f"{df.height} rows, fewer than the deployed {previous.height}")
    if df["year"].max() < previous["year"].max():
        failures.append(
            f"latest year {df['year'].max()} is older than the deployed "
            f"{previous['year'].max()}",
        )
    return failures


def main() -> None:
    """Validate a dataset and exit non-zero if any check fails."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("path", type=Path, help="parquet file to validate")
    parser.add_argument("--previous", type=Path, help="currently deployed parquet")
    args = parser.parse_args()

    df = pl.read_parquet(args.path)
    failures = check_structure(df)
    if not failures:
        failures = check_values(df)
    if args.previous is not None:
        failures += check_against_previous(df, pl.read_parquet(args.previous))

    if failures:
        print(f"FAILED: {len(failures)} check(s) on {args.path}")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)
    print(f"OK: {args.path} passed all checks ({df.height} rows)")


if __name__ == "__main__":
    main()

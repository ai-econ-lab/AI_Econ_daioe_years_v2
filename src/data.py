"""Data loading, lazy frame, and data-derived input constants."""

from pathlib import Path

import polars as pl

from .constants import AGE_ORDER

BASE_DIR = Path(__file__).resolve().parent.parent

INTRO_MD: str = (BASE_DIR / "md_files" / "intro.md").read_text(encoding="utf-8")

_ABOUT_TEMPLATE: str = (BASE_DIR / "md_files" / "about.md").read_text(encoding="utf-8")

DATA_PATH = BASE_DIR / "data" / "daioe_scb_years_processed.parquet"

lf = pl.read_parquet(DATA_PATH).lazy()

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
    """Return a dict mapping each SSYK level to its sorted occupation choices.

    At SSYK4 the labels are bilingual (English · Svenska), so the selectize
    search matches Swedish occupation names too (prast, pastor, HR, ...);
    values stay the English occupation strings the rest of the app filters on.
    """
    df_occs = (
        lf.select(["level", "occupation", "ssyk_code"])
        .unique(subset=["level", "occupation"])
        .sort(["level", "occupation"])
        .collect()
    )
    sv_path = DATA_PATH.parent / "svenska_titlar.csv"
    sv: dict[str, str] = {}
    if sv_path.exists():
        sv_df = pl.read_csv(sv_path, schema_overrides={"ssyk_code": pl.Utf8})
        sv = dict(zip(sv_df["ssyk_code"].to_list(), sv_df["svensk_titel"].to_list()))
    out: dict[str, dict[str, str]] = {}
    for lvl in levels:
        sub = df_occs.filter(pl.col("level") == lvl)
        pairs = zip(sub["occupation"].to_list(), sub["ssyk_code"].cast(pl.Utf8).to_list())
        if lvl == "SSYK4" and sv:
            out[lvl] = {
                o: (f"{o} \u00b7 {sv[c]}" if c in sv and sv[c] != o else o)
                for o, c in pairs
            }
        else:
            out[lvl] = {o: o for o, _ in pairs}
    return out


def build_options_by_level(
    lf: pl.LazyFrame,
    levels: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Selectize option objects per level, with an invisible search field.

    label: "English · Svenska" at SSYK4 (both languages visible and searchable);
    sok: curated bilingual keywords (colloquial titles, abbreviations) from
    data/sok_nyckelord.csv, searchable but not displayed.
    """
    df_occs = (
        lf.select(["level", "occupation", "ssyk_code"])
        .unique(subset=["level", "occupation"])
        .sort(["level", "occupation"])
        .collect()
    )
    sv: dict[str, str] = {}
    p = DATA_PATH.parent / "svenska_titlar.csv"
    if p.exists():
        f = pl.read_csv(p, schema_overrides={"ssyk_code": pl.Utf8})
        sv = dict(zip(f["ssyk_code"].to_list(), f["svensk_titel"].to_list()))
    kw: dict[str, str] = {}
    p = DATA_PATH.parent / "sok_nyckelord.csv"
    if p.exists():
        f = pl.read_csv(p, schema_overrides={"ssyk_code": pl.Utf8})
        kw = dict(zip(f["ssyk_code"].to_list(), f["keywords"].to_list()))
    out: dict[str, list[dict[str, str]]] = {}
    for lvl in levels:
        sub = df_occs.filter(pl.col("level") == lvl)
        opts = []
        for o, c in zip(sub["occupation"].to_list(), sub["ssyk_code"].cast(pl.Utf8).to_list()):
            label = f"{o} \u00b7 {sv[c]}" if lvl == "SSYK4" and c in sv and sv[c] != o else o
            opts.append({"value": o, "label": label, "sok": kw.get(c, "")})
        out[lvl] = opts
    return out

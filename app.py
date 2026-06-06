from pathlib import Path

import faicons as fa
import polars as pl
from shiny import reactive, render
from shiny.express import app_opts, ui
from shiny.express import input as app_input
from shinywidgets import render_widget

from src.calcs import (
    get_comp_radar,
    get_comp_summary,
    get_comparison_employment,
    get_occ_ai_exposure,
    get_occ_employment_by_age,
    get_occ_summary,
)
from src.constants import FIRST_COLS, METRICS
from src.data import (
    ABOUT_MD,
    AGES,
    INTRO_MD,
    LEVELS,
    SEXES,
    YEAR_MAX,
    YEAR_MIN,
    YEARS,
    build_choices_by_level,
    lf,
)
from src.utils import (
    as_great_table_html,
    download_extension,
    download_media_type,
    export_filtered_data,
)
from src.visuals import (
    build_age_chart,
    build_ai_exposure_bar,
    build_comp_radar_plot,
    build_comparison_employment_plot,
    build_employment_count_chart,
    build_value_boxes,
    export_fig,
)

import kaleido

kaleido.start_sync_server(silence_warnings=True)

LOGOS_PATH = Path(__file__).parent / "logos"
app_opts(static_assets={"/logos": LOGOS_PATH})

ui.page_opts(
    fillable=True,
    theme=ui.Theme.from_brand(__file__),
    lang="en",
    full_width=True,
)

LEVEL_LABELS = {
    "SSYK1": "SSYK 1 - Major groups",
    "SSYK2": "SSYK 2 - Minor groups",
    "SSYK3": "SSYK 3 - Unit groups",
    "SSYK4": "SSYK 4 - Detailed units",
}
OCCUPATION_CHOICES = build_choices_by_level(lf, LEVELS)
DEFAULT_LEVEL = "SSYK4" if "SSYK4" in LEVELS else LEVELS[0]
DEFAULT_OCCUPATION = next(iter(OCCUPATION_CHOICES[DEFAULT_LEVEL]))
_LEVEL_CHOICES = {level: LEVEL_LABELS.get(level, level) for level in LEVELS}


def _parse_comp_occs(
    selected: list[str],
    comp_level: str,
) -> list[tuple[str, str]]:
    """Parse selected comp_occs values into (level, occupation) pairs.

    For a specific level, returns [(comp_level, occ), ...].
    For All Levels, values are encoded as "LEVEL|occupation" and parsed here.
    """
    if comp_level == "All Levels":
        result = []
        for v in selected:
            if "|" not in v:
                continue  # stale plain-name value from previous level; skip until UI re-encodes
            lvl, occ = v.split("|", 1)
            result.append((lvl, occ))
        return result
    return [(comp_level, occ) for occ in selected]


def _occ_display_col(df: pl.DataFrame, is_all_levels: bool) -> pl.DataFrame:
    """Append the SSYK level to occupation labels when comparing across levels.

    Ensures duplicate occupation names from different levels render as distinct
    series in charts and rows in tables.
    """
    if "level" not in df.columns:
        return df
    if is_all_levels:
        return df.with_columns(
            (pl.col("occupation") + " [" + pl.col("level") + "]").alias("occupation"),
        ).drop("level")
    return df.drop("level")


# ── Tab navigation ────────────────────────────────────────────

with ui.navset_pill(id="main_tabs"):
    # ── Tab 1: Single Occupation ──────────────────────────────

    with ui.nav_panel("Single Occupation"), ui.layout_sidebar():
        with ui.sidebar(title="Single Occupation", width=280):
            ui.div(
                ui.img(
                    src="/logos/lab.svg",
                    alt="AI-Econ Lab logo",
                    style="width:100%; max-width:180px;",
                ),
                style="text-align:center; margin-bottom:1rem;",
            )
            ui.markdown(INTRO_MD)
            ui.hr()
            ui.input_select(
                "occ_level",
                "SSYK Level",
                choices=_LEVEL_CHOICES,
                selected=DEFAULT_LEVEL,
            )
            ui.p(
                "Sets the occupational detail level and updates the occupation list.",
                class_="text-muted small mt-n1 mb-2",
            )
            ui.input_selectize(
                "occupation",
                "Occupation",
                choices=OCCUPATION_CHOICES[DEFAULT_LEVEL],
                selected=DEFAULT_OCCUPATION,
                options={"placeholder": "Search occupation..."},
            )
            ui.p(
                "Updates value boxes, AI exposure chart, and both employment charts.",
                class_="text-muted small mt-n1 mb-2",
            )
            ui.input_select(
                "occ_year",
                "Year",
                choices={str(y): str(y) for y in YEARS},
                selected=str(YEAR_MAX),
            )
            ui.p(
                "Year for AI exposure scores and value boxes.",
                class_="text-muted small mt-n1 mb-2",
            )
            ui.hr()
            ui.p("Employment trend filters:", class_="fw-semibold mb-1 small")
            ui.p(
                "Controls the year range and age groups shown in both employment charts.",
                class_="text-muted small mt-0 mb-2",
            )
            ui.input_slider(
                "chart_year_range",
                "Year range",
                min=YEAR_MIN,
                max=YEAR_MAX,
                value=[YEAR_MIN, YEAR_MAX],
                step=1,
                sep="",
            )
            ui.input_selectize(
                "chart_age_groups",
                "Age groups",
                choices=AGES,
                selected=AGES[:2],
                multiple=True,
            )
            ui.p(
                "Select one or more age groups to display as separate lines in the employment charts. Each line tracks that age group's trend over the selected year range.",
                class_="text-muted small mt-n1 mb-2",
            )
            ui.input_selectize(
                "chart_sex",
                "Gender overlay",
                choices={"men": "Men", "women": "Women"},
                selected=[],
                multiple=True,
            )
            ui.p(
                "Overlay individual gender breakdowns alongside the aggregate series.",
                class_="text-muted small mt-n1 mb-2",
            )

        # Value boxes (outside cards)
        @render.ui
        def occ_value_boxes():
            summary = occ_summary()
            if summary is None:
                return ui.p(
                    "No data for the selected occupation and year.",
                    class_="text-muted p-3",
                )
            return build_value_boxes(summary, app_input.occupation())

        # Stacked chart cards
        with ui.layout_columns(col_widths=12):
            with ui.card(full_screen=True, height="700px"):
                with ui.card_header(class_="d-flex align-items-center gap-2"):
                    ui.span("Annual Employment Change by Age Group")
                    with ui.popover(placement="bottom"):
                        fa.icon_svg("circle-info", height="1.2em")
                        "Year-over-year percentage change in employment by age group. Values above zero indicate growth; below zero indicate decline."
                    with ui.span(class_="ms-auto"):

                        @render.download(
                            filename=lambda: (
                                f"{app_input.occupation().replace(' ', '_')}_employment_by_age.png"
                            ),
                            media_type="image/png",
                            label=ui.span(
                                fa.icon_svg("download"), title="Download as PNG"
                            ),
                        )
                        def dl_occ_age_chart():
                            yield export_fig(
                                build_age_chart(
                                    occ_employment_by_age_pd(),
                                    app_input.occupation(),
                                ),
                            )

                @render_widget
                def occ_age_chart():
                    return build_age_chart(
                        occ_employment_by_age_pd(), app_input.occupation()
                    )

            with ui.card(full_screen=True, height="700px"):
                with ui.card_header(class_="d-flex align-items-center gap-2"):
                    ui.span("Employment by Age Group")
                    with ui.popover(placement="bottom"):
                        fa.icon_svg("circle-info", height="1.2em")
                        "Absolute headcount by age group over the selected year range. Hover to see the 1-year percentage change."
                    with ui.span(class_="ms-auto"):

                        @render.download(
                            filename=lambda: (
                                f"{app_input.occupation().replace(' ', '_')}_employment_count.png"
                            ),
                            media_type="image/png",
                            label=ui.span(
                                fa.icon_svg("download"), title="Download as PNG"
                            ),
                        )
                        def dl_occ_count_chart():
                            yield export_fig(
                                build_employment_count_chart(
                                    occ_employment_by_age_pd(),
                                    app_input.occupation(),
                                ),
                            )

                @render_widget
                def occ_count_chart():
                    return build_employment_count_chart(
                        occ_employment_by_age_pd(), app_input.occupation()
                    )

            with ui.card(full_screen=True, height="700px"):
                with ui.card_header(class_="d-flex align-items-center gap-2"):
                    ui.span("AI Exposure by Sub-Domain")
                    with ui.popover(placement="bottom"):
                        fa.icon_svg("circle-info", height="1.2em")
                        "Each bar shows how this occupation ranks against all others for that AI sub-domain. Higher percentile = higher relative AI exposure."
                    with ui.span(class_="ms-auto"):

                        @render.download(
                            filename=lambda: (
                                f"{app_input.occupation().replace(' ', '_')}_ai_exposure.png"
                            ),
                            media_type="image/png",
                            label=ui.span(
                                fa.icon_svg("download"), title="Download as PNG"
                            ),
                        )
                        def dl_ai_bar():
                            yield export_fig(
                                build_ai_exposure_bar(
                                    occ_ai_exposure_pd(),
                                    app_input.occupation(),
                                    int(app_input.occ_year()),
                                ),
                            )

                @render_widget
                def occ_ai_bar():
                    return build_ai_exposure_bar(
                        occ_ai_exposure_pd(),
                        app_input.occupation(),
                        int(app_input.occ_year()),
                    )

    # ── Tab 2: Compare Occupations ────────────────────────────

    with ui.nav_panel("Compare Occupations"), ui.layout_sidebar():
        with ui.sidebar(title="Compare Occupations", width=280):
            ui.input_select(
                "comp_level",
                "SSYK Level",
                choices={"All Levels": "All Levels", **_LEVEL_CHOICES},
                selected=DEFAULT_LEVEL,
            )
            ui.input_selectize(
                "comp_occs",
                "Occupations",
                choices={},
                multiple=True,
                options={"maxItems": 5, "placeholder": "Search occupation..."},
            )
            ui.p(
                "Select up to five occupations to compare.",
                class_="text-muted small mt-n1 mb-2",
            )
            ui.input_selectize(
                "comp_age",
                "Age Groups",
                choices=AGES,
                selected=AGES[:2],
                multiple=True,
            )
            ui.input_select(
                "comp_year",
                "Year",
                choices={str(y): str(y) for y in YEARS},
                selected=str(YEAR_MAX),
            )
            ui.p(
                "Year for the AI radar chart and summary table.",
                class_="text-muted small mt-n1 mb-2",
            )

        # Occupations summary table
        with ui.card(fill=True, fillable=True):
            ui.card_header("Occupations Summary")

            @render.ui
            def comp_summary_table():
                occs = list(app_input.comp_occs() or [])
                ages = list(app_input.comp_age() or [])
                if not occs or not ages:
                    return ui.p(
                        "Select occupations and age groups from the sidebar to compare.",
                        class_="text-muted p-3",
                    )
                pairs = _parse_comp_occs(occs, app_input.comp_level())
                df = get_comp_summary(lf, pairs, int(app_input.comp_year()), ages)
                df = _occ_display_col(df, app_input.comp_level() == "All Levels")
                return ui.div(
                    as_great_table_html(df.to_pandas(), METRICS),
                    style="overflow: auto; width: 100%; height: 100%;",
                )

        # AI percentile radar chart
        with ui.card(full_screen=True, height="700px"):
            with ui.card_header(class_="d-flex align-items-center gap-2"):
                ui.span("AI Exposure Comparison (percentile rank)")
                with ui.popover(placement="bottom"):
                    fa.icon_svg("circle-info", height="1.2em")
                    "Each axis shows a percentile rank (0-100). Outer position = higher relative AI exposure than other occupations."
                with ui.span(class_="ms-auto"):

                    @render.download(
                        filename="ai_radar.png",
                        media_type="image/png",
                        label=ui.span(fa.icon_svg("download"), title="Download as PNG"),
                    )
                    def dl_comp_radar():
                        yield export_fig(
                            build_comp_radar_plot(
                                comp_radar_data_pd(),
                                METRICS,
                            ),
                        )

            @render_widget
            def comp_radar_chart():
                return build_comp_radar_plot(comp_radar_data_pd(), METRICS)

        # Employment comparison line chart
        with ui.card(full_screen=True, height="700px"):
            with ui.card_header(class_="d-flex align-items-center gap-2"):
                ui.span("Annual Employment Change")
                with ui.popover(placement="bottom"):
                    fa.icon_svg("circle-info", height="1.2em")
                    "1-year percentage change in employment for each selected occupation and the selected age groups."
                with ui.span(class_="ms-auto"):

                    @render.download(
                        filename="comparison_employment.png",
                        media_type="image/png",
                        label=ui.span(fa.icon_svg("download"), title="Download as PNG"),
                    )
                    def dl_comp_employment():
                        yield export_fig(
                            build_comparison_employment_plot(
                                comparison_data_pd(),
                            ),
                        )

            @render_widget
            def comp_employment_chart():
                return build_comparison_employment_plot(comparison_data_pd())

    # ── Tab 3: Download Data ──────────────────────────────────

    with ui.nav_panel("Download Data"), ui.layout_sidebar():
        with ui.sidebar(title="Download Filters", width=280):
            ui.input_select(
                "download_level",
                "SSYK Level",
                choices=_LEVEL_CHOICES,
                selected=DEFAULT_LEVEL,
            )
            ui.input_slider(
                "download_years",
                "Year range",
                min=YEAR_MIN,
                max=YEAR_MAX,
                value=[YEAR_MIN, YEAR_MAX],
                step=1,
                sep="",
            )
            ui.input_checkbox_group(
                "download_sex",
                "Gender",
                choices={"men": "Men", "women": "Women"},
                selected=SEXES,
                inline=True,
            )
            ui.input_select(
                "download_age",
                "Age Group",
                choices={"All": "All ages"} | {a: a for a in AGES},
                selected="All",
            )
            ui.input_selectize(
                "download_occupation",
                "Occupations",
                choices=OCCUPATION_CHOICES[DEFAULT_LEVEL],
                multiple=True,
                options={"placeholder": "Leave empty to include all..."},
            )
            ui.input_select(
                "download_format",
                "Format",
                choices={"csv": "CSV", "parquet": "Parquet", "excel": "Excel"},
                selected="csv",
            )
            ui.hr()

            @render.download(
                filename=lambda: (
                    "daioe_swedish_occupations_"
                    f"{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}."
                    f"{download_extension(app_input.download_format())}"
                ),
                media_type=lambda: download_media_type(app_input.download_format()),
                label="Download",
            )
            def download_data():
                """Export filtered data in the selected format."""
                yield export_filtered_data(
                    download_frame().to_pandas(),
                    app_input.download_format(),
                )

        ui.p(
            "Export row-level yearly occupation data including employment counts, "
            "percentage changes, and AI exposure scores. Use the sidebar to filter by "
            "level, year range, gender, age group, and occupation.",
            class_="text-muted mb-3",
        )

        with ui.layout_columns(col_widths=[6, 6]):
            with ui.value_box(theme="primary"):
                "Rows"

                @render.text
                def dl_row_count():
                    return f"{download_frame().height:,}"

            with ui.value_box(theme="primary"):
                "Columns"

                @render.text
                def dl_col_count():
                    return f"{download_frame().width:,}"

        with ui.card(full_screen=True):
            ui.card_header("Data Preview (first 50 rows)")

            @render.ui
            def dl_preview():
                df = download_frame()
                all_cols = df.columns
                ordered = [c for c in FIRST_COLS if c in all_cols]
                rest = [c for c in all_cols if c not in ordered]
                return as_great_table_html(
                    df.select(ordered + rest).head(50).to_pandas(),
                    METRICS,
                )

    # ── Tab 4: About ──────────────────────────────────────────

    with ui.nav_panel("About"), ui.card(fill=True, fillable=True):
        ui.card_header("About This Dashboard")
        ui.div(
            ui.img(
                src="/logos/lab.svg",
                alt="AI-Econ Lab logo",
                style="height:60px; display:block; margin:1rem 0 1.5rem;",
            ),
        )
        ui.markdown(ABOUT_MD)


# ── Reactive calculations ─────────────────────────────────────


@reactive.calc
def occ_summary():
    return get_occ_summary(
        lf,
        app_input.occ_level(),
        app_input.occupation(),
        int(app_input.occ_year()),
    )


@reactive.calc
def occ_ai_exposure():
    return get_occ_ai_exposure(
        lf,
        app_input.occ_level(),
        app_input.occupation(),
        int(app_input.occ_year()),
    )


@reactive.calc
def occ_employment_by_age():
    yr = app_input.chart_year_range()
    ages = list(app_input.chart_age_groups() or [])
    extra_sexes = tuple(app_input.chart_sex() or [])
    if not ages:
        return pl.DataFrame(
            schema={
                "year": pl.Int64,
                "age_group": pl.String,
                "count": pl.Float64,
                "chg_1y": pl.Float64,
                "pct_chg_1y": pl.Float64,
                "sex": pl.String,
                "series": pl.String,
            },
        )
    return get_occ_employment_by_age(
        lf,
        app_input.occ_level(),
        app_input.occupation(),
        (int(yr[0]), int(yr[1])),
        ages,
        extra_sexes,
    )


@reactive.calc
def comparison_data():
    occs = list(app_input.comp_occs() or [])
    ages = list(app_input.comp_age() or [])
    if not occs or not ages:
        return pl.DataFrame(
            schema={
                "year": pl.Int64,
                "occupation": pl.String,
                "count": pl.Int64,
                "pct_chg_1y": pl.Float64,
            },
        )
    pairs = _parse_comp_occs(occs, app_input.comp_level())
    df = get_comparison_employment(lf, pairs, ages)
    return _occ_display_col(df, app_input.comp_level() == "All Levels")


@reactive.calc
def comp_radar_data():
    occs = list(app_input.comp_occs() or [])
    if not occs:
        return pl.DataFrame()
    pairs = _parse_comp_occs(occs, app_input.comp_level())
    df = get_comp_radar(lf, pairs, int(app_input.comp_year()))
    return _occ_display_col(df, app_input.comp_level() == "All Levels")


@reactive.calc
def occ_employment_by_age_pd():
    return occ_employment_by_age().to_pandas()


@reactive.calc
def occ_ai_exposure_pd():
    return occ_ai_exposure().to_pandas()


@reactive.calc
def comparison_data_pd():
    return comparison_data().to_pandas()


@reactive.calc
def comp_radar_data_pd():
    return comp_radar_data().to_pandas()


@reactive.calc
def download_frame():
    years = app_input.download_years()
    q = lf.filter(
        (pl.col("level") == app_input.download_level())
        & pl.col("year").is_between(int(years[0]), int(years[1])),
    )
    sexes = list(app_input.download_sex())
    if sexes:
        q = q.filter(pl.col("sex").is_in(sexes))
    age = app_input.download_age()
    if age != "All":
        q = q.filter(pl.col("age_group") == age)
    occupations = list(app_input.download_occupation())
    if occupations:
        q = q.filter(pl.col("occupation").is_in(occupations))
    return q.collect()


# ── Reactive effects ──────────────────────────────────────────


@reactive.effect
def _sync_occupation_choices():
    """Update the occupation selectize choices whenever the SSYK level changes."""
    level = app_input.occ_level()
    choices = OCCUPATION_CHOICES[level]
    ui.update_selectize("occupation", choices=choices, selected=next(iter(choices)))


@reactive.effect
def _sync_comp_occupation_choices():
    """Update comparison occupation choices when the SSYK level changes.

    For All Levels mode, keys are encoded as "LEVEL|occupation" and labels show the
    level in brackets so duplicate occupation names across levels are distinguishable.
    """
    level = app_input.comp_level()
    if level == "All Levels":
        choices = {
            f"{lvl}|{occ}": f"{occ} [{LEVEL_LABELS.get(lvl, lvl)}]"
            for lvl in LEVELS
            for occ in OCCUPATION_CHOICES[lvl]
        }
    else:
        choices = OCCUPATION_CHOICES.get(level, {})
    default_two = list(choices)[:2]
    ui.update_selectize("comp_occs", choices=choices, selected=default_two)


@reactive.effect
def _sync_download_occupation_choices():
    """Update the download occupation selectize when the download SSYK level changes."""
    level = app_input.download_level()
    ui.update_selectize(
        "download_occupation",
        choices=OCCUPATION_CHOICES[level],
        selected=[],
    )

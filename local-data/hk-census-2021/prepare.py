# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Prepare the published 2021 district profile, never individual census records."""

from __future__ import annotations

import csv
import hashlib
import io
import json  # noqa: TID251 -- Standalone tools do not import the Superset runtime.
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parent
ARCHIVE_URL = "https://www.censtatd.gov.hk/en/data/stat_report/product/D5212109/att/D5212109B2021XXXXB.zip"
RESOURCE_URL = "https://data.gov.hk/en-data/dataset/hk-censtatd-census21c-d5212109/resource/34eeab77-54d2-423c-803b-b2a68c7345fb"
SYMBOLS_URL = "https://www.census2021.gov.hk/doc/pub/21c-main-results.pdf"
TABLE_PREFIX = "public.hk_census_2021_"
DISTRICT_CODES = {
    "11",
    "12",
    "13",
    "14",
    "23",
    "24",
    "25",
    "26",
    "27",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
}


class DatasetSpecification(TypedDict):
    """Native MCP dataset creation input."""

    key: str
    name: str
    sql: str
    description: str


class ChartSpecification(TypedDict):
    """Native MCP chart input and its intended tab."""

    key: str
    tab: str
    name: str
    dataset: str
    config: dict[str, object]


class Specifications(TypedDict):
    """A reviewed resource inventory, independent of renderer implementation."""

    dashboard_title: str
    database_id: int
    datasets: list[DatasetSpecification]
    charts: list[ChartSpecification]
    tabs: list[str]


class Validation(TypedDict):
    """Reconciled source facts."""

    districts: int
    cells: int
    indicator_count: int
    totals: dict[str, int]
    reconciled_families: list[str]
    elderly_share: str


def clean_label(value: str) -> str:
    """Remove footnote markers and invisible characters, retaining their metadata."""
    return re.sub(r"\(\d+\)", "", value.replace("\u200c", "")).strip()


def validate_sql_token(value: str) -> None:
    """Accept only source identifiers, never SQL fragments in generated snapshots."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid source identifier")


def parse_value(raw: str) -> tuple[Decimal | None, str]:
    """Follow the 2021 Main Results symbol legend, retaining the original token."""
    if raw == "-":
        return Decimal(0), "published_nil"
    if raw in {"..", "."}:
        return None, "not_applicable"
    if raw in {"N.A.", ""}:
        return None, "not_available"
    return Decimal(raw), "published"


def measure_metadata(topic: str) -> tuple[str, str]:
    """Classify units and safe aggregation from the published field definition."""
    text = topic.lower()
    kind = "count"
    if "median" in text:
        kind = "median"
    elif "average" in text:
        kind = "average"
    elif "rate" in text or "proportion" in text or "ratio" in text:
        kind = "rate"
    rules = [
        ("income ratio" in text, "percent"),
        (kind == "count" and "households" in text, "households"),
        ("hk$" in text, "HKD" if kind != "count" else "persons"),
        ("square metres" in text, "square metres"),
        ("median age" in text, "years"),
        ("sex ratio" in text, "males per 1,000 females"),
        (kind == "rate", "percent"),
        (kind == "average", "persons per household"),
        ("occupied quarters" in text, "quarters"),
        ("households" in text, "households"),
    ]
    unit = next((unit for matches, unit in rules if matches), "persons")
    return kind, unit


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write deterministic columns using UTF-8 for native Superset upload."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_cells(
    geographies: list[dict[str, object]], cells: list[dict[str, object]]
) -> Validation:
    """Check geographic completeness, additive families and published references."""
    districts = {
        str(g["district_code"])
        for g in geographies
        if g["geography_kind"] == "district"
    }
    if districts != DISTRICT_CODES:
        raise ValueError("The 18 district codes do not match the 2021 source contract")
    values = {
        (str(c["district_code"]), str(c["indicator_code"])): Decimal(
            str(c["numeric_value"])
        )
        for c in cells
        if c["numeric_value"] is not None
    }
    if len(cells) != 19 * 205 or len(
        {(c["district_code"], c["indicator_code"]) for c in cells}
    ) != len(cells):
        raise ValueError(
            "Expected exactly one cell per geography and published indicator"
        )
    checks = {
        "population": (["pop_m", "pop_f"], "t_pop"),
        "age": ([f"age_{i}" for i in range(1, 6)], "t_pop"),
        "household_size": ([f"dhz_{i}" for i in range(1, 7)], "dh"),
        "household_income": ([f"dhi_{i}" for i in range(1, 8)], "dh"),
        "household_housing": (["dh_pub", "dh_s", "dh_pri", "dh_non", "dh_tem"], "dh"),
        "tenure": (["dh_ocm", "dh_ocwm", "dh_st", "dh_co", "dh_rf", "dh_emp"], "dh"),
    }
    for geo in districts | {"99"}:
        for name, (codes, total) in checks.items():
            if sum(values[(geo, code)] for code in codes) != values[(geo, total)]:
                raise ValueError(f"{geo}: {name} does not reconcile")
    totals = {
        code: int(sum(values[(d, code)] for d in districts))
        for code in ["t_pop", "dh", "age_5", "t_wp", "t_lf"]
    }
    expected = {
        "t_pop": 7411945,
        "dh": 2673714,
        "age_5": 1451444,
        "t_wp": 3680407,
        "t_lf": 3942678,
    }
    if totals != expected:
        raise ValueError(f"Source differs from the reviewed release: {totals}")
    for code in expected:
        if values[("99", code)] != totals[code]:
            raise ValueError(f"Land reference does not reconcile: {code}")
    return {
        "districts": len(districts),
        "cells": len(cells),
        "indicator_count": 205,
        "totals": totals,
        "reconciled_families": list(checks),
        "elderly_share": str(Decimal(totals["age_5"]) / Decimal(totals["t_pop"])),
    }


def summary_sql(release_id: str) -> str:
    """Pivot district observations without combining non-additive indicators."""
    fields = {
        "population": "t_pop",
        "domestic_households": "dh",
        "elderly_population": "age_5",
        "working_population": "t_wp",
        "labour_force": "t_lf",
        "children_population": "age_1",
        "median_age": "t_ma",
        "average_household_size": "adhz",
        "median_household_income_hkd": "ma_hh",
        "labour_force_participation_percent": "lfpr_t",
        "median_floor_area_sqm": "fa_m",
        "median_monthly_rent_hkd": "dm_r",
        "median_rent_to_income_percent": "dmr_ir",
        "median_monthly_mortgage_hkd": "dhm_loan",
        "median_mortgage_to_income_percent": "dhm_lr",
    }
    pivots = ",\n  ".join(
        f"MAX(CASE WHEN c.indicator_code = '{code}' THEN c.numeric_value END) "
        f"AS {label}"
        for label, code in fields.items()
    )
    validate_sql_token(release_id)
    # Tokens are validated and tables/columns are workflow-owned constants.
    return f"""SELECT g.district_code, g.district_name, g.region, 2021 AS census_year,
  {pivots},
  100.0 * MAX(CASE WHEN c.indicator_code = 'age_5' THEN c.numeric_value END)
    / NULLIF(MAX(CASE WHEN c.indicator_code = 't_pop'
        THEN c.numeric_value END), 0) AS elderly_share_percent
FROM {TABLE_PREFIX}cell c
JOIN {TABLE_PREFIX}geography g ON c.district_code = g.district_code
WHERE c.release_id = '{release_id}' AND g.geography_kind = 'district'
GROUP BY g.district_code, g.district_name, g.region"""


def distribution_sql(
    release_id: str, codes: list[str], *, ordered: bool = False, marital: bool = False
) -> str:
    """Expose only one mutually exclusive published distribution per dataset."""
    validate_sql_token(release_id)
    for code in codes:
        validate_sql_token(code)
    code_list = ", ".join(f"'{code}'" for code in codes)
    order = (
        "i.category_order::text || '. ' || i.category_en"
        if ordered
        else "i.category_en"
    )
    sex = (
        "CASE WHEN RIGHT(c.indicator_code, 1) = 'm' THEN 'Male' ELSE 'Female' END"
        if marital
        else "NULL::text"
    )
    return f"""SELECT g.district_code, g.district_name, g.region, 2021 AS census_year,
  {order} AS category_label, i.category_en AS source_category,
  i.category_order, {sex} AS sex, c.numeric_value AS count_value,
  i.unit, i.universe, i.footnotes, c.indicator_code, c.value_status
FROM {TABLE_PREFIX}cell c
JOIN {TABLE_PREFIX}geography g ON g.district_code = c.district_code
JOIN {TABLE_PREFIX}indicator i ON i.indicator_code = c.indicator_code
WHERE c.release_id = '{release_id}' AND g.geography_kind = 'district'
  AND c.indicator_code IN ({code_list})"""


def specifications(release_id: str) -> Specifications:
    """Describe resources for native MCP provisioning, with no renderer settings."""
    validate_sql_token(release_id)
    datasets: list[DatasetSpecification] = [
        {
            "key": "summary",
            "name": "HK Census 2021 - District summary",
            "sql": summary_sql(release_id),
            "description": (
                "One row per 2021 district. Counts are additive. "
                "Published medians, means and rates are per "
                "district only. 18 land districts exclude Marine."
            ),
        }
    ]
    charts: list[ChartSpecification] = []

    def add(
        key: str, tab: str, name: str, dataset: str, config: dict[str, object]
    ) -> None:
        charts.append(
            {"key": key, "tab": tab, "name": name, "dataset": dataset, "config": config}
        )

    for key, title, column in [
        ("population", "Population", "population"),
        ("households", "Domestic households", "domestic_households"),
        ("working", "Working population", "working_population"),
    ]:
        add(
            key,
            "Overview",
            title,
            "summary",
            {
                "chart_type": "big_number",
                "metric": {"name": column, "aggregate": "SUM", "label": title},
                "y_axis_format": ",.0f",
            },
        )
    add(
        "elderly",
        "Overview",
        "Population aged 65+ share",
        "summary",
        {
            "chart_type": "big_number",
            "metric": {
                "name": "elderly_population",
                "aggregate": "SUM",
                "ratio_denominator": "population",
                "label": "Population aged 65+ share",
            },
            "y_axis_format": ".1%",
        },
    )

    def district_bar(
        key: str,
        tab: str,
        title: str,
        column: str,
        *,
        additive: bool = False,
        fmt: str = ",.0f",
    ) -> None:
        add(
            key,
            tab,
            title,
            "summary",
            {
                "chart_type": "xy",
                "kind": "bar",
                "orientation": "horizontal",
                "x": {"name": "district_name"},
                "y": [
                    {
                        "name": column,
                        "aggregate": "SUM" if additive else "MAX",
                        "label": title,
                    }
                ],
                "sort_by_value": "desc",
                "show_value_sort_control": True,
                "y_axis": {"format": fmt},
                "legend": {"show": False},
                "row_limit": 18,
            },
        )

    district_bar(
        "population_district",
        "Overview",
        "Population by district",
        "population",
        additive=True,
    )
    summary_columns = {
        "district_name": "District",
        "population": "Population",
        "domestic_households": "Domestic Households",
        "elderly_share_percent": "Population Aged 65+ (%)",
        "median_age": "Median Age",
        "average_household_size": "Average Household Size",
        "median_household_income_hkd": "Median Monthly Household Income (HKD)",
        "labour_force_participation_percent": "Labour Force Participation (%)",
    }
    add(
        "district_table",
        "Overview",
        "District comparison - published indicators",
        "summary",
        {
            "chart_type": "table",
            "query_mode": "raw",
            "columns": [{"name": k, "label": v} for k, v in summary_columns.items()],
            "row_limit": 18,
            "sort_by": ["district_name"],
        },
    )

    def distribution(
        key: str,
        tab: str,
        title: str,
        codes: list[str],
        *,
        donut: bool = False,
        ordered: bool = False,
        marital: bool = False,
        description: str = "",
    ) -> None:
        datasets.append(
            {
                "key": key,
                "name": f"HK Census 2021 - {title}",
                "sql": distribution_sql(
                    release_id, codes, ordered=ordered, marital=marital
                ),
                "description": description
                or (
                    "Published aggregate distribution. Combine counts across "
                    "districts; no joint filters from unrelated statistical "
                    "populations. Official source definitions and footnotes "
                    "are included in the source-cell dataset."
                ),
            }
        )
        if donut:
            config: dict[str, object] = {
                "chart_type": "pie",
                "dimension": {"name": "category_label"},
                "metric": {"name": "count_value", "aggregate": "SUM", "label": "Count"},
                "donut": True,
                "label_type": "percent",
                "label_color": "#FFFFFF",
                "labels_outside": False,
                "show_total": True,
                "show_legend": True,
                "inner_radius": 45,
                "outer_radius": 75,
                "number_format": ",.0f",
                "row_limit": 30,
            }
        else:
            config = {
                "chart_type": "xy",
                "kind": "bar",
                "orientation": "horizontal",
                "x": {"name": "category_label"},
                "y": [
                    {
                        "name": "count_value",
                        "aggregate": "SUM",
                        "label": "Households"
                        if key.startswith("household")
                        or key in {"housing", "tenure", "rooms"}
                        else "Persons",
                    }
                ],
                "legend": {"show": marital, "position": "top"},
                "y_axis": {"format": ",.0f"},
                "row_limit": 50,
            }
            if not ordered:
                config["sort_by_value"] = "desc"
            if marital:
                config["group_by"] = [{"name": "sex"}]
        add(key, tab, title, key, config)

    people = "People and diversity"
    distribution(
        "age",
        people,
        "Population by age band",
        [f"age_{i}" for i in range(1, 6)],
        ordered=True,
    )
    distribution("sex", people, "Population by sex", ["pop_m", "pop_f"], donut=True)
    distribution(
        "marital",
        people,
        "Marital status by sex - population aged 15+",
        [
            "ms_nm_m",
            "ms_ma_m",
            "ms_win_m",
            "ms_div_m",
            "ms_sep_m",
            "ms_nm_f",
            "ms_m_f",
            "ms_win_f",
            "ms_div_f",
            "ms_sep_f",
        ],
        marital=True,
    )
    distribution(
        "birthplace",
        people,
        "Population by birthplace",
        ["born_hk", "born_chi", "born_else"],
        donut=True,
    )
    distribution(
        "ethnicity",
        people,
        "Population by ethnicity",
        ["ethn_chi", "ethn_phi", "ethn_ind", "ethn_wh", "ethn_oth"],
    )
    distribution(
        "language",
        people,
        "Usual spoken language - population aged 5+",
        ["ul_can", "ul_put", "ul_othchi", "ul_eng", "ul_oth"],
        description=(
            "Population aged 5 and over, excluding mute persons. "
            "Usual spoken language is not language proficiency."
        ),
    )
    households = "Households and income"
    distribution(
        "household_size",
        households,
        "Domestic household size",
        [f"dhz_{i}" for i in range(1, 7)],
        ordered=True,
    )
    distribution(
        "household_composition",
        households,
        "Domestic household composition",
        [f"dhc_{i}" for i in range(1, 9)],
    )
    distribution(
        "household_income",
        households,
        "Monthly domestic household income bands (HKD)",
        [f"dhi_{i}" for i in range(1, 8)],
        ordered=True,
    )
    district_bar(
        "median_household_income",
        households,
        "Median monthly household income by district (HKD)",
        "median_household_income_hkd",
    )
    distribution(
        "housing",
        "Housing",
        "Domestic households by housing type",
        ["dh_pub", "dh_s", "dh_pri", "dh_non", "dh_tem"],
        donut=True,
    )
    distribution(
        "tenure",
        "Housing",
        "Domestic households by tenure",
        ["dh_ocm", "dh_ocwm", "dh_st", "dh_co", "dh_rf", "dh_emp"],
    )
    distribution(
        "rooms",
        "Housing",
        "Rooms excluding kitchens and bathrooms",
        [f"dh_r{i}" for i in range(1, 7)] + ["dh_r0"],
        ordered=True,
    )
    housing_columns = {
        "district_name": "District",
        "median_floor_area_sqm": "Median Floor Area (m2)",
        "median_monthly_rent_hkd": "Median Monthly Rent (HKD)",
        "median_rent_to_income_percent": "Median Rent to Income (%)",
        "median_monthly_mortgage_hkd": "Median Monthly Mortgage Payment (HKD)",
        "median_mortgage_to_income_percent": "Median Mortgage Payment to Income (%)",
    }
    add(
        "housing_table",
        "Housing",
        "Housing costs and space - published district medians",
        "summary",
        {
            "chart_type": "table",
            "query_mode": "raw",
            "columns": [{"name": k, "label": v} for k, v in housing_columns.items()],
            "row_limit": 18,
            "sort_by": ["district_name"],
        },
    )
    work = "Education and work"
    distribution(
        "education",
        work,
        "Highest level attended - population aged 15+",
        [
            "edu_prepri",
            "edu_pri",
            "edu_lsed",
            "edu_usec",
            "edu_dip",
            "edu_sub",
            "edu_deg",
        ],
        ordered=True,
    )
    distribution(
        "employment",
        work,
        "Working population by employment status",
        ["wp_ee", "wp_er", "wp_se", "wp_fw"],
        donut=True,
    )
    distribution(
        "occupation",
        work,
        "Working population by occupation",
        [f"wp_{letter}" for letter in "abcdefghi"],
    )
    distribution(
        "industry",
        work,
        "Working population by industry",
        [f"wp_{letter}" for letter in "jklmnopqrst"],
    )
    distribution(
        "employment_income",
        work,
        "Monthly employment income (HKD) - excluding helpers and unpaid family workers",
        [f"mearn_xfdhfw_{i}" for i in range(1, 8)],
        ordered=True,
    )
    district_bar(
        "labour_rate",
        work,
        "Labour force participation by district (%)",
        "labour_force_participation_percent",
        fmt=",.1f",
    )
    mobility = "Mobility and sources"
    distribution(
        "workplace",
        mobility,
        "Working population by place of work",
        [
            "plw_same",
            "plw_diff_hk",
            "plw_diff_kln",
            "plw_diff_nt",
            "plw_diff_oth",
            "plw_nofix",
            "plw_hm",
            "plw_out",
        ],
        description=(
            "Uses the official same-district/new-town definition; "
            "work at home is separate. District of residence is the "
            "geographic filter."
        ),
    )
    distribution(
        "studyplace",
        mobility,
        "Full-time students by place of study",
        ["pls_same", "pls_diff_hk", "pls_diff_kln", "pls_diff_nt", "s_diff_oth"],
        description=(
            "Full-time study in Hong Kong institutions. Same-district"
            " uses the official district/new-town definition."
        ),
    )
    migration_codes = [
        "pm_hk",
        "pm_kln",
        "pm_nt",
        "pm_oth",
        "pm_samearea",
        "pm_same",
        "pm_out",
    ]
    datasets.append(
        {
            "key": "migration_status",
            "name": "HK Census 2021 - Migration status",
            "description": (
                "Population aged 5 and over. Internal migration is"
                " the official change of area over the preceding "
                "five years, including some moves between new "
                "towns within a district."
            ),
            "sql": distribution_sql(release_id, migration_codes).replace(
                "i.category_en AS category_label",
                (
                    "CASE WHEN c.indicator_code IN "
                    "('pm_hk','pm_kln','pm_nt','pm_oth') THEN 'Internally "
                    "migrated' WHEN c.indicator_code = 'pm_samearea' THEN "
                    "'Moved within same area' WHEN c.indicator_code = 'pm_same'"
                    " THEN 'Remained at same address' ELSE 'Previously outside "
                    "Hong Kong' END AS category_label"
                ),
            ),
        }
    )
    add(
        "migration_status",
        mobility,
        "Residence change over preceding five years - population aged 5+",
        "migration_status",
        {
            "chart_type": "xy",
            "kind": "bar",
            "orientation": "horizontal",
            "x": {"name": "category_label"},
            "y": [{"name": "count_value", "aggregate": "SUM", "label": "Persons"}],
            "legend": {"show": False},
            "sort_by_value": "desc",
            "y_axis": {"format": ",.0f"},
            "row_limit": 10,
        },
    )
    distribution(
        "migration_origin",
        mobility,
        "Previous area of residence - internal migrants aged 5+",
        migration_codes[:4],
    )
    source_sql = f"""SELECT
  g.district_code, g.district_name, g.region, 2021 AS census_year,
  i.topic_en AS source_topic, i.category_en AS category, i.indicator_code,
  c.numeric_value AS published_value, c.raw_value, c.value_status,
  i.unit, i.universe, i.measure_kind, i.footnotes, r.resource_url AS source_url
FROM {TABLE_PREFIX}cell c
JOIN {TABLE_PREFIX}geography g ON g.district_code = c.district_code
JOIN {TABLE_PREFIX}indicator i ON i.indicator_code = c.indicator_code
JOIN {TABLE_PREFIX}release r ON r.release_id = c.release_id
WHERE c.release_id = '{release_id}' AND g.geography_kind = 'district'"""
    datasets.append(
        {
            "key": "source",
            "name": "HK Census 2021 - Published source cells",
            "sql": source_sql,
            "description": (
                "Published district aggregates, not individual "
                "census records. Original values, symbols, "
                "statistical populations and bilingual metadata "
                "are retained in physical tables."
            ),
        }
    )
    source_columns = {
        "district_name": "District",
        "source_topic": "Source Topic",
        "category": "Category",
        "published_value": "Published Value",
        "unit": "Unit",
        "raw_value": "Original Value",
        "value_status": "Source Status",
        "indicator_code": "Source Field",
        "universe": "Statistical Population",
        "footnotes": "Source Notes",
        "source_url": "Source URL",
    }
    add(
        "source",
        mobility,
        "Published census source cells",
        "source",
        {
            "chart_type": "table",
            "query_mode": "raw",
            "columns": [{"name": k, "label": v} for k, v in source_columns.items()],
            "sort_by": ["district_name", "source_topic"],
            "row_limit": 10000,
        },
    )
    assert len(charts) == 31
    for chart in charts:
        config = chart["config"]
        sort_by = config.get("sort_by")
        if isinstance(sort_by, list):
            config["sort_by"] = [json.dumps([name, True]) for name in sort_by]
    return {
        "dashboard_title": "Hong Kong Census 2021 - People, Households and Districts",
        "database_id": 1,
        "datasets": datasets,
        "charts": charts,
        "tabs": ["Overview", people, households, "Housing", work, mobility],
    }


def prepare() -> dict[str, object]:
    """Download and validate a source snapshot, then prepare native MCP inputs."""
    snapshot = ROOT / "snapshot"
    snapshot.mkdir(exist_ok=True)
    request = urllib.request.Request(  # noqa: S310 -- Fixed official HTTPS endpoint.
        ARCHIVE_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.censtatd.gov.hk/en/scode470.html",
        },
    )
    archive = urllib.request.urlopen(request, timeout=60).read()  # noqa: S310
    csv_bytes = zipfile.ZipFile(io.BytesIO(archive)).read("DC_21C.CSV")
    (snapshot / "official-archive.zip").write_bytes(archive)
    (snapshot / "DC_21C.CSV").write_bytes(csv_bytes)
    rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    if len(rows[4]) != 209 or rows[4][:5] != [
        "dc_class",
        "dc",
        "dc_eng",
        "dc_chi",
        "t_pop",
    ]:
        raise ValueError(
            "Unexpected source headers; review the new release before import"
        )
    codes = rows[4]
    source_data = [row for row in rows[5:] if len(row) == 209 and row[1].isdigit()]
    sha = hashlib.sha256(csv_bytes).hexdigest()
    release_id = f"dc2021-{sha[:12]}"
    notes = {}
    for row in rows[24:]:
        for value in row:
            match = re.match(r"\((\d+)\) - (.*)", value)
            if match and any("a" <= ch.lower() <= "z" for ch in match[2]):
                notes[match[1]] = match[2]
    geographies: list[dict[str, object]] = []
    for row in source_data:
        region = {"1": "Hong Kong Island", "2": "Kowloon", "3": "New Territories"}.get(
            row[1][0], "Land reference"
        )
        geographies.append(
            {
                "district_code": row[1],
                "district_class": row[0],
                "district_name": row[2],
                "district_name_zh": row[3],
                "region": region,
                "geography_kind": "district"
                if row[1] in DISTRICT_CODES
                else "land_reference",
                "boundary_year": 2021,
            }
        )
    indicators: list[dict[str, object]] = []
    group_positions: dict[str, int] = {}
    for index, code in enumerate(codes[4:], 4):
        topic = rows[1][index]
        category = rows[3][index]
        group_positions[topic] = group_positions.get(topic, 0) + 1
        kind, unit = measure_metadata(topic)
        refs = sorted(set(re.findall(r"\((\d+)\)", topic + " " + category)), key=int)
        indicators.append(
            {
                "indicator_code": code,
                "topic_en": clean_label(topic),
                "topic_zh": rows[0][index],
                "category_en": clean_label(category),
                "category_zh": rows[2][index],
                "category_order": 0 if code == "dh_r0" else group_positions[topic],
                "measure_kind": kind,
                "unit": unit,
                "universe": clean_label(topic),
                "aggregation_rule": "SUM" if kind == "count" else "district_only",
                "footnotes": " ".join(f"({n}) {notes[n]}" for n in refs if n in notes),
            }
        )
    cells: list[dict[str, object]] = []
    for row in source_data:
        for index, code in enumerate(codes[4:], 4):
            numeric_value, status = parse_value(row[index])
            cells.append(
                {
                    "release_id": release_id,
                    "district_code": row[1],
                    "indicator_code": code,
                    "census_year": 2021,
                    "raw_value": row[index],
                    "numeric_value": numeric_value,
                    "value_status": status,
                }
            )
    validation = validate_cells(geographies, cells)
    release = [
        {
            "release_id": release_id,
            "census_year": 2021,
            "resource_url": RESOURCE_URL,
            "download_url": ARCHIVE_URL,
            "file_name": "DC_21C.CSV",
            "csv_sha256": sha,
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "resource_updated_date": "2026-04-27",
            "provider": "Census and Statistics Department",
            "symbols_url": SYMBOLS_URL,
            "coverage": "18 land districts; code 99 is a separate Land total reference",
            "source_notes_json": json.dumps(notes, ensure_ascii=False),
        }
    ]
    for table, records in [
        ("release", release),
        ("geography", geographies),
        ("indicator", indicators),
        ("cell", cells),
    ]:
        write_csv(snapshot / f"hk_census_2021_{table}.csv", records)
    spec = specifications(release_id)
    (snapshot / "specifications.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    provenance = {
        "release": release[0],
        "validation": validation,
        "whole_hong_kong_reference": {
            "population": 7413070,
            "domestic_households": 2674161,
            "source_url": "https://www.censtatd.gov.hk/en/scode470.html",
            "used_in_district_aggregation": False,
        },
        "source_symbols": {
            "-": "published nil; preserve sampling caveat",
            "..": "not applicable",
            "N.A.": "not available",
        },
    }
    (ROOT / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        **validation,
        "dataset_count": len(spec["datasets"]),
        "chart_count": len(spec["charts"]),
        "release_id": release_id,
    }


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))

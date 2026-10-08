# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
"""Validate live APIs using recorded, synthetic native resources, never census data."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from http_client import Client

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / ".runtime/localization-test-resources.json"
BASE = "/extensions/focalbi/content-localization/catalog"
client = Client("http://localhost:8088", ROOT / ".runtime/admin-cookie.json")


def check(condition: bool, message: str) -> None:
    """Stop on failed acceptance assertions."""
    if not condition:
        raise RuntimeError(message)


def expect_status(path: str, data: Any, status: int, method: str = "PUT") -> None:
    """Assert native HTTP status without exposing session credentials."""
    try:
        client.request(path, data, method)
    except RuntimeError as error:
        check(str(error).startswith(f"HTTP {status}:"), str(error))
        return
    raise RuntimeError(f"Expected HTTP {status}")


def create_fixture() -> dict[str, Any]:
    """Provision test-only resources through native APIs and record each UUID."""
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    state: dict[str, Any] = {"owner": "focalbi.localization.tests", "resources": []}

    def create(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = client.request(f"/api/v1/{kind}/", payload, "POST")
        native_id = result["id"]
        resource = client.request(f"/api/v1/{kind}/{native_id}")["result"]
        item = {"type": kind, "id": native_id, "uuid": resource["uuid"]}
        state["resources"].append(item)
        LEDGER.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return item

    dataset = create(
        "dataset",
        {
            "database": 1,
            "table_name": "Localization QA synthetic regions " + uuid4().hex[:8],
            "sql": """SELECT * FROM (VALUES
        ('North', DATE '2024-01-01', 40::numeric, 0.4::numeric, 'Alpha'),
        ('South', DATE '2024-06-01', 60::numeric, 0.6::numeric, 'Beta'),
        ('North', DATE '2025-01-01', 20::numeric, 0.2::numeric, 'Beta'),
        ('South', DATE '2025-06-01', 80::numeric, 0.8::numeric, 'Alpha')
        ) AS sample(region_code,event_on,amount_total,share_ratio,theme_group)""",
        },
    )
    metric = {
        "expressionType": "SIMPLE",
        "aggregate": "SUM",
        "column": {"column_name": "amount_total"},
        "label": "Sample amount",
        "optionName": "qa_amount",
        "hasCustomLabel": True,
    }
    definitions = [
        {
            "viz_type": "pie",
            "groupby": ["region_code"],
            "metric": metric,
            "show_legend": True,
            "show_labels": True,
            "label_type": "key_value_percent",
        },
        {
            "viz_type": "table",
            "query_mode": "raw",
            "all_columns": ["event_on", "region_code", "amount_total", "theme_group"],
            "include_search": True,
            "page_length": 2,
            "column_config": {
                "event_on": {
                    "customColumnName": "Sample date",
                    "d3TimeFormat": "%d/%m/%Y",
                }
            },
        },
        {
            "viz_type": "big_number_total",
            "metric": metric,
            "subheader": "Synthetic total",
        },
        {
            "viz_type": "echarts_timeseries_bar",
            "x_axis": "region_code",
            "metrics": [metric],
            "orientation": "horizontal",
            "x_axis_title": "Region axis",
            "y_axis_title": "Amount axis",
        },
        {
            "viz_type": "mixed_timeseries",
            "x_axis": "event_on",
            "granularity_sqla": "event_on",
            "time_grain_sqla": "P1Y",
            "metrics": [metric],
            "metrics_b": [
                {
                    **metric,
                    "column": {"column_name": "share_ratio"},
                    "label": "Sample share",
                    "optionName": "qa_share",
                }
            ],
            "seriesType": "line",
            "seriesTypeB": "line",
            "area": True,
            "areaB": True,
            "yAxisIndex": 0,
            "yAxisIndexB": 1,
            "zoomable": True,
            "show_legend": True,
            "x_axis_title": "Sample year",
            "y_axis_title": "Sample amount",
            "y_axis_title_secondary": "Sample share",
        },
    ]
    dashboard = create(
        "dashboard",
        {"dashboard_title": "Localization synthetic regions", "published": True},
    )
    layout: dict[str, Any] = {"DASHBOARD_VERSION_KEY": "v2"}

    def node(
        key: str,
        kind: str,
        children: list[str],
        parents: list[str],
        meta: dict[str, Any],
    ) -> None:
        layout[key] = {
            "id": key,
            "type": kind,
            "children": children,
            "parents": parents,
            "meta": meta,
        }

    node("ROOT_ID", "ROOT", ["GRID_ID"], [], {})
    node("GRID_ID", "GRID", ["TABS-QA"], ["ROOT_ID"], {})
    node("TABS-QA", "TABS", ["TAB-QA-0", "TAB-QA-1"], ["ROOT_ID", "GRID_ID"], {})
    for tab in range(2):
        node(
            f"TAB-QA-{tab}",
            "TAB",
            [],
            ["ROOT_ID", "GRID_ID", "TABS-QA"],
            {"text": ["Details", "Trends"][tab]},
        )
    for index, params in enumerate(definitions):
        params = {
            "row_limit": 100,
            "time_range": "No filter",
            **params,
            "datasource": f"{dataset['id']}__table",
        }
        chart = create(
            "chart",
            {
                "slice_name": "Synthetic " + params["viz_type"],
                "description": "Synthetic **regional** example. Not census statistics.",
                "viz_type": params["viz_type"],
                "datasource_id": dataset["id"],
                "datasource_type": "table",
                "params": json.dumps(params),
                "dashboards": [dashboard["id"]],
            },
        )
        tab = 0 if index < 2 else 1
        tab_key = f"TAB-QA-{tab}"
        row = f"ROW-QA-{index}"
        chart_key = f"CHART-QA-{index}"
        parents = ["ROOT_ID", "GRID_ID", "TABS-QA", tab_key]
        layout[tab_key]["children"].append(row)
        node(row, "ROW", [chart_key], parents, {"background": "BACKGROUND_TRANSPARENT"})
        node(
            chart_key,
            "CHART",
            [],
            [*parents, row],
            {
                "chartId": chart["id"],
                "width": 12,
                "height": 40,
                "sliceName": "Synthetic " + params["viz_type"],
            },
        )
    filter_id = "NATIVE_FILTER-localization-qa"
    metadata = {
        "native_filter_configuration": [
            {
                "id": filter_id,
                "name": "Sample region",
                "description": "Choose raw region codes",
                "filterType": "filter_select",
                "targets": [
                    {"datasetId": dataset["id"], "column": {"name": "region_code"}}
                ],
                "controlValues": {
                    "multiSelect": True,
                    "enableEmptyFilter": False,
                    "searchAllOptions": False,
                    "inverseSelection": False,
                },
                "defaultDataMask": {
                    "extraFormData": {},
                    "filterState": {"value": None},
                },
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "cascadeParentIds": [],
                "type": "NATIVE_FILTER",
            }
        ]
    }
    client.request(
        f"/api/v1/dashboard/{dashboard['id']}",
        {"position_json": json.dumps(layout), "json_metadata": json.dumps(metadata)},
        "PUT",
    )
    state["dashboard"] = dashboard
    state["dataset"] = dataset
    state["charts"] = [item for item in state["resources"] if item["type"] == "chart"]
    LEDGER.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


fixture = create_fixture()
check(fixture.get("owner") == "focalbi.localization.tests", "Unowned fixture ledger")
for item in fixture["resources"]:
    path = f"{BASE}/resource/{item['type']}/{item['uuid']}"
    catalog = client.request(path)["result"]
    entries = {}
    for descriptor in catalog["fields"]:
        key, source = descriptor["key"], descriptor["source"]
        if descriptor["kind"] == "category":
            dictionary = (
                [
                    {"value": value, "values": {"zh-Hant": "地區", "zh-Hans": "地区"}}
                    for value in ["North", "South"]
                ]
                if descriptor.get("target") == "region_code"
                else []
            )
            entries[key] = {
                "sourceHash": descriptor["sourceHash"],
                "values": {},
                "dictionary": dictionary,
            }
        else:
            entries[key] = {
                "sourceHash": descriptor["sourceHash"],
                "values": {
                    "en": source,
                    "zh-Hant": "繁體 " + source,
                    "zh-Hans": "简体 " + source,
                },
                "dictionary": [],
            }
    current = client.request(
        path, {"revision": catalog["revision"], "entries": entries}, "PUT"
    )["result"]
    expect_status(path, {"revision": catalog["revision"], "entries": entries}, 409)
    expect_status(
        path,
        {
            "revision": current["revision"],
            "entries": {"unknown": {"values": {"en": "bad"}}},
        },
        400,
    )
    exported = client.request(f"{BASE}/export/{item['type']}/{item['uuid']}")["result"]
    expected = {
        key: {
            **entry,
            "values": {
                locale: value for locale, value in entry["values"].items() if value
            },
        }
        for key, entry in entries.items()
    }
    check(
        exported["resources"][0]["entries"] == expected,
        "Export preserves nonblank authored entries",
    )

catalogs = [
    client.request(f"{BASE}/export/chart/{item['uuid']}")["result"]["resources"][0]
    for item in fixture["charts"][:2]
]
revisions = [item["revision"] for item in catalogs]
catalogs[1]["revision"] += 100
expect_status(f"{BASE}/import", {"version": 1, "resources": catalogs}, 409, "POST")
for item, revision in zip(catalogs, revisions, strict=True):
    current = client.request(f"{BASE}/resource/chart/{item['uuid']}")["result"]
    check(current["revision"] == revision, "Failed batch import rolls back all writes")
catalogs[1]["revision"] = revisions[1]
client.request(
    f"{BASE}/import", {"version": 1, "resources": catalogs, "remap": {}}, "POST"
)

dashboard = fixture["dashboard"]
bundle = client.request(f"{BASE}/bundle/dashboard/{dashboard['uuid']}?locale=zh-Hant")[
    "result"
]
check(len(bundle["charts"]) == 5, "All unrelated visualization types discovered")
dataset_resource = bundle["resources"][f"dataset/{fixture['dataset']['uuid']}"]
dictionary = next(
    entry["dictionary"]
    for entry in dataset_resource["translations"].values()
    if len(entry["dictionary"]) == 2
)
check(
    dictionary[0]["label"] == dictionary[1]["label"],
    "Duplicate labels remain separate raw values",
)
check(dictionary[0]["value"] != dictionary[1]["value"], "Raw identities preserved")

chart = fixture["charts"][0]
path = f"{BASE}/resource/chart/{chart['uuid']}"
original = client.request(f"/api/v1/chart/{chart['id']}")["result"]["slice_name"]
try:
    client.request(
        f"/api/v1/chart/{chart['id']}", {"slice_name": original + " changed"}, "PUT"
    )
    stale = client.request(f"{BASE}/bundle/chart/{chart['uuid']}?locale=zh-Hant")[
        "result"
    ]
    check(
        "title" not in stale["resources"][f"chart/{chart['uuid']}"]["translations"],
        "Changed original suspends translation",
    )
finally:
    client.request(f"/api/v1/chart/{chart['id']}", {"slice_name": original}, "PUT")

report = {
    "passed": True,
    "types": ["dataset", "chart", "dashboard"],
    "independentColumns": True,
    "revisionConflict": True,
    "unknownFieldsRejected": True,
    "export": True,
    "atomicImport": True,
    "sourceChangeFallback": True,
    "duplicateLabelsRawIdentity": True,
    "dashboardId": dashboard["id"],
    "nativeResourcesRecorded": True,
}
(ROOT / "test-results/live-api.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(json.dumps(report))

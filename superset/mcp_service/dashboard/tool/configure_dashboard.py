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
"""Configure native dashboard controls without changing access or publishing."""

from typing import Annotated, Any

from fastmcp import Context
from pydantic import BaseModel, Field
from superset_core.mcp.decorators import tool, ToolAnnotations

from superset.mcp_service.dashboard.constants import generate_id
from superset.utils import json


class DashboardSelectFilter(BaseModel):
    """A select control restricted to a dataset already used on the dashboard."""

    name: str = Field(min_length=1, max_length=150)
    dataset_id: int = Field(gt=0)
    column: str = Field(min_length=1, max_length=255)
    default_values: list[str | int | float] = Field(default_factory=list)
    key: str | None = Field(None, pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    scope_chart_ids: list[int] | None = Field(None, min_length=1, max_length=100)


class ConfigureDashboardRequest(BaseModel):
    """Add or update select filters, colors, and an optional overview layout."""

    dashboard_id: int = Field(gt=0)
    filters: list[DashboardSelectFilter] = Field(default_factory=list, max_length=20)
    label_colors: dict[str, Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]] = (
        Field(default_factory=dict)
    )
    remove_filter_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Remove specified native filters from this dashboard.",
    )
    overview_layout: bool = Field(
        False,
        description="Replace layout: KPI row, paired charts and full-width tables.",
    )
    introduction: str | None = Field(
        None,
        max_length=10000,
        description="Markdown source/methodology note; used only with overview_layout.",
    )
    full_width_chart_ids: list[int] = Field(
        default_factory=list,
        max_length=100,
        description="Dashboard charts to place in taller full-width overview rows.",
    )
    remove_chart_ids: list[int] = Field(
        default_factory=list,
        max_length=100,
        description="Detach charts from this dashboard when rebuilding its overview; "
        "does not delete saved charts or affect other dashboards.",
    )


def remove_native_filters(filters: dict[str, Any], filter_ids: list[str]) -> None:
    """Remove dashboard-owned controls while preserving cascade dependencies."""
    if not set(filter_ids).issubset(filters):
        raise ValueError("Removed filters must belong to this dashboard")
    for filter_id in filter_ids:
        if any(
            filter_id in item.get("cascadeParentIds", [])
            for item in filters.values()
            if item["id"] not in filter_ids
        ):
            raise ValueError("Cannot remove a filter used by another filter")
        del filters[filter_id]


def build_select_filter(
    spec: DashboardSelectFilter, chart_ids: list[int] | None = None
) -> dict[str, Any]:
    """Use a stable ID so repeated configuration updates the same filter."""
    import hashlib

    identity = f"{spec.dataset_id}:{spec.column}"
    if spec.key:
        identity += f":{spec.key}"
    key = hashlib.sha256(identity.encode()).hexdigest()[:12]
    excluded = []
    if spec.scope_chart_ids is not None:
        if chart_ids is None or not set(spec.scope_chart_ids).issubset(chart_ids):
            raise ValueError("Filter scope must contain only dashboard charts")
        excluded = sorted(set(chart_ids) - set(spec.scope_chart_ids))
    values = spec.default_values
    return {
        "id": f"NATIVE_FILTER-MCP-{key}",
        "name": spec.name,
        "filterType": "filter_select",
        "type": "NATIVE_FILTER",
        "targets": [{"datasetId": spec.dataset_id, "column": {"name": spec.column}}],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": excluded},
        "cascadeParentIds": [],
        "controlValues": {
            "enableEmptyFilter": False,
            "defaultToFirstItem": False,
            "multiSelect": True,
            "searchAllOptions": True,
            "inverseSelection": False,
        },
        "defaultDataMask": {
            "extraFormData": {
                "filters": [{"col": spec.column, "op": "IN", "val": values}]
            }
            if values
            else {},
            "filterState": {
                "value": values or None,
                "label": ", ".join(map(str, values)),
            },
            "ownState": {},
        },
    }


def overview_layout(
    charts: list[Any],
    introduction: str | None,
    full_width_chart_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Build a layout containing each supplied chart exactly once."""
    layout: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
        "GRID_ID": {
            "id": "GRID_ID",
            "type": "GRID",
            "parents": ["ROOT_ID"],
            "children": [],
        },
    }
    if introduction:
        key = generate_id("MARKDOWN")
        layout[key] = {
            "id": key,
            "type": "MARKDOWN",
            "parents": ["ROOT_ID", "GRID_ID"],
            "children": [],
            "meta": {"code": introduction, "width": 12, "height": 32},
        }
        layout["GRID_ID"]["children"].append(key)
    full_width = set(full_width_chart_ids or [])
    if not full_width.issubset({c.id for c in charts}):
        raise ValueError("Full-width charts must belong to this dashboard")
    wide = [c for c in charts if c.id in full_width]
    charts = [c for c in charts if c.id not in full_width]
    kpis = [c for c in charts if c.viz_type in {"big_number_total", "big_number"}]
    plots = [
        c
        for c in charts
        if c not in kpis and c.viz_type not in {"table", "ag-grid-table"}
    ]
    tables = [c for c in charts if c.viz_type in {"table", "ag-grid-table"}]
    groups = [(kpis[i : i + 3], 20) for i in range(0, len(kpis), 3)]
    groups += [(plots[i : i + 2], 50) for i in range(0, len(plots), 2)]
    groups += [([c], 75) for c in wide]
    groups += [([c], 60) for c in tables]
    for group, height in groups:
        row = generate_id("ROW")
        layout[row] = {
            "id": row,
            "type": "ROW",
            "parents": ["ROOT_ID", "GRID_ID"],
            "children": [],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        layout["GRID_ID"]["children"].append(row)
        width = 12 // len(group)
        for chart in group:
            key = f"CHART-{chart.id}"
            layout[key] = {
                "id": key,
                "type": "CHART",
                "parents": ["ROOT_ID", "GRID_ID", row],
                "children": [],
                "meta": {
                    "chartId": chart.id,
                    "uuid": str(chart.uuid),
                    "sliceName": chart.slice_name,
                    "width": width,
                    "height": height,
                },
            }
            layout[row]["children"].append(key)
    return layout


def select_dashboard_charts(
    charts: list[Any], request: ConfigureDashboardRequest
) -> list[Any]:
    """Validate removal scope before changing the chart relationship or layout."""
    removed = set(request.remove_chart_ids)
    if removed and (
        not request.overview_layout or not removed.issubset({c.id for c in charts})
    ):
        raise ValueError(
            "Chart removal requires overview_layout and dashboard membership"
        )
    return [c for c in charts if c.id not in removed]


@tool(
    tags=["mutate"],
    class_permission_name="Dashboard",
    method_permission_name="write",
    annotations=ToolAnnotations(
        title="Configure dashboard controls", readOnlyHint=False, destructiveHint=False
    ),
)
def configure_dashboard(
    request: ConfigureDashboardRequest, ctx: Context
) -> dict[str, Any]:
    """Upsert native select filters and label colors on an owned dashboard.

    Filters must reference columns from datasets already used by accessible charts.
    Other filters and metadata are preserved. Does not publish or change permissions.
    overview_layout explicitly replaces the layout, including existing tabs/text.
    """
    from superset import security_manager
    from superset.commands.dashboard.update import UpdateDashboardCommand
    from superset.daos.dashboard import DashboardDAO
    from superset.mcp_service.auth import check_chart_data_access

    dashboard = DashboardDAO.find_by_id(request.dashboard_id)
    if dashboard is None:
        raise ValueError("Dashboard not found")
    security_manager.raise_for_ownership(dashboard)
    datasets = {}
    charts = sorted(dashboard.slices, key=lambda c: c.id)
    for chart in charts:
        validation = check_chart_data_access(chart)
        if not validation.is_valid:
            raise ValueError(f"Chart {chart.id} is not accessible")
        if chart.datasource_type == "table" and chart.datasource:
            datasets[chart.datasource_id] = chart.datasource
    for spec in request.filters:
        dataset = datasets.get(spec.dataset_id)
        if dataset is None or spec.column not in {
            c.column_name for c in dataset.columns
        }:
            raise ValueError(
                f"Filter {spec.name} must use a column from a dashboard dataset"
            )
    charts = select_dashboard_charts(charts, request)
    metadata = json.loads(dashboard.json_metadata or "{}")
    filters = {f["id"]: f for f in metadata.get("native_filter_configuration", [])}
    remove_native_filters(filters, request.remove_filter_ids)
    for spec in request.filters:
        item = build_select_filter(spec, [c.id for c in charts])
        filters[item["id"]] = item
    metadata["native_filter_configuration"] = list(filters.values())
    metadata.setdefault("label_colors", {}).update(request.label_colors)
    properties: dict[str, Any] = {"json_metadata": json.dumps(metadata)}
    if request.remove_chart_ids:
        properties["slices"] = charts
    if request.overview_layout:
        properties["position_json"] = json.dumps(
            overview_layout(charts, request.introduction, request.full_width_chart_ids)
        )
    UpdateDashboardCommand(request.dashboard_id, properties).run()
    return {
        "dashboard_id": request.dashboard_id,
        "filter_count": len(filters),
        "success": True,
    }

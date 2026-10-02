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
"""Verify filter isolation, authorization, and layout preservation through MCP."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from superset.mcp_service.app import mcp
from superset.mcp_service.dashboard.tool.configure_dashboard import (
    build_select_filter,
    ConfigureDashboardRequest,
    DashboardSelectFilter,
    overview_layout,
    select_dashboard_charts,
)
from superset.utils import json


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "owner", "dataset", "column", "access"])
async def test_configure_checks_access_and_preserves_metadata(
    failure: str | None,
) -> None:
    dataset = SimpleNamespace(columns=[SimpleNamespace(column_name="year")])
    chart = SimpleNamespace(
        id=1, datasource_id=22, datasource_type="table", datasource=dataset
    )
    old_filter = {"id": "existing", "name": "Keep me"}
    dashboard = SimpleNamespace(
        slices=[chart],
        json_metadata=json.dumps(
            {
                "native_filter_configuration": [old_filter],
                "cross_filters_enabled": False,
                "label_colors": {"Existing": "#123456"},
                "refresh_frequency": 60,
            }
        ),
    )
    request = {
        "dashboard_id": 11,
        "filters": [
            {
                "name": "Year",
                "dataset_id": 999 if failure == "dataset" else 22,
                "column": "absent" if failure == "column" else "year",
                "default_values": [2025],
            }
        ],
        "label_colors": {"FDS": "#087F8C"},
    }
    with (
        patch(
            "superset.mcp_service.auth.get_user_from_request",
            return_value=Mock(id=1, username="admin"),
        ),
        patch(
            "superset.daos.dashboard.DashboardDAO.find_by_id", return_value=dashboard
        ),
        patch(
            "superset.security_manager.raise_for_ownership",
            side_effect=ValueError("No ownership") if failure == "owner" else None,
        ),
        patch(
            "superset.mcp_service.auth.check_chart_data_access",
            return_value=SimpleNamespace(is_valid=failure != "access"),
        ),
        patch("superset.commands.dashboard.update.UpdateDashboardCommand") as update,
    ):
        async with Client(mcp) as client:
            if failure:
                with pytest.raises(ToolError):
                    await client.call_tool("configure_dashboard", {"request": request})
                update.assert_not_called()
            else:
                await client.call_tool("configure_dashboard", {"request": request})
                properties = update.call_args.args[1]
                assert "position_json" not in properties
                assert "published" not in properties
                assert "roles" not in properties
                metadata = json.loads(properties["json_metadata"])
                assert metadata["native_filter_configuration"][0] == old_filter
                assert metadata["refresh_frequency"] == 60
                assert metadata["label_colors"] == {
                    "Existing": "#123456",
                    "FDS": "#087F8C",
                }
                update.return_value.run.assert_called_once()


def test_removal_is_limited_to_this_dashboard_and_requires_layout_rebuild() -> None:
    charts = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    request = ConfigureDashboardRequest(
        dashboard_id=11, overview_layout=True, remove_chart_ids=[2]
    )
    assert select_dashboard_charts(charts, request) == [charts[0]]
    assert len(charts) == 2
    for invalid in [
        request.model_copy(update={"overview_layout": False}),
        request.model_copy(update={"remove_chart_ids": [3]}),
    ]:
        with pytest.raises(ValueError, match="dashboard membership"):
            select_dashboard_charts(charts, invalid)


def test_filter_defaults_are_real_query_predicates() -> None:
    spec = DashboardSelectFilter(
        name="Year", dataset_id=22, column="year", default_values=[2025]
    )
    item = build_select_filter(spec)
    assert item["defaultDataMask"]["extraFormData"]["filters"] == [
        {"col": "year", "op": "IN", "val": [2025]}
    ]
    assert item["id"] == build_select_filter(spec)["id"]
    assert (
        build_select_filter(spec.model_copy(update={"default_values": []}))[
            "defaultDataMask"
        ]["extraFormData"]
        == {}
    )


def test_scoped_filters_have_distinct_ids_and_exact_exclusions() -> None:
    spec = DashboardSelectFilter(
        name="Annual year",
        dataset_id=22,
        column="year",
        key="annual-year",
        scope_chart_ids=[119],
    )
    annual = build_select_filter(spec, [118, 119, 121])
    assert annual["scope"]["excluded"] == [118, 121]
    themes = build_select_filter(
        spec.model_copy(update={"key": "themes-year", "scope_chart_ids": [121]}),
        [118, 119, 121],
    )
    assert annual["id"] != themes["id"]
    assert themes["scope"]["excluded"] == [118, 119]
    with pytest.raises(ValueError, match="only dashboard charts"):
        build_select_filter(spec, [118, 121])


def test_overview_contains_each_chart_once_with_valid_grid_widths() -> None:
    charts = [
        SimpleNamespace(id=i, uuid=str(i), slice_name=str(i), viz_type=kind)
        for i, kind in enumerate(
            [
                "big_number_total",
                "big_number_total",
                "big_number_total",
                "pie",
                "echarts_timeseries_bar",
                "table",
            ]
        )
    ]
    layout = overview_layout(charts, "Source note")
    rendered = [
        v["meta"]["chartId"]
        for v in layout.values()
        if isinstance(v, dict) and v.get("type") == "CHART"
    ]
    assert sorted(rendered) == list(range(6))
    for v in layout.values():
        if isinstance(v, dict) and v.get("type") == "ROW":
            assert sum(layout[c]["meta"]["width"] for c in v["children"]) == 12
    assert layout["CHART-5"]["meta"]["width"] == 12
    wide_layout = overview_layout(charts, "Source note", [4])
    assert wide_layout["CHART-4"]["meta"]["width"] == 12
    assert wide_layout["CHART-4"]["meta"]["height"] == 75
    assert sorted(
        v["meta"]["chartId"]
        for v in wide_layout.values()
        if isinstance(v, dict) and v.get("type") == "CHART"
    ) == list(range(6))
    with pytest.raises(ValueError, match="belong to this dashboard"):
        overview_layout(charts, None, [999])


def test_filter_removal_validates_membership_and_cascades() -> None:
    from superset.mcp_service.dashboard.tool.configure_dashboard import (
        remove_native_filters,
    )

    filters = {
        "category": {"id": "category"},
        "year": {"id": "year", "cascadeParentIds": ["category"]},
        "other": {"id": "other"},
    }
    with pytest.raises(ValueError, match="belong to this dashboard"):
        remove_native_filters(filters, ["unknown"])
    with pytest.raises(ValueError, match="used by another filter"):
        remove_native_filters(filters, ["category"])
    remove_native_filters(filters, ["year", "category"])
    assert filters == {"other": {"id": "other"}}

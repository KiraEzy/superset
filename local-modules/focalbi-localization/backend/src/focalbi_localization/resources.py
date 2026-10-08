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
"""Read-only, version-pinned adapters to native saved resource definitions."""

from __future__ import annotations

import json
from typing import Any

from flask import g
from superset.connectors.sqla.models import SqlaTable
from superset.extensions import db, security_manager
from superset.models.dashboard import Dashboard
from superset.models.slice import Slice

from .catalog import fingerprint, identity

SUPPORTED = {
    "big_number_total",
    "pie",
    "echarts_timeseries_bar",
    "mixed_timeseries",
    "table",
}
TEXT_CONTROLS = (
    "x_axis_title",
    "y_axis_title",
    "y_axis_title_secondary",
    "subtitle",
    "subheader",
    "header",
    "label",
    "description",
)
VIZ_CONTROLS = {
    "big_number_total": ("subheader",),
    "pie": (),
    "echarts_timeseries_bar": ("x_axis_title", "y_axis_title"),
    "mixed_timeseries": ("x_axis_title", "y_axis_title", "y_axis_title_secondary"),
    "table": (),
}


def load(kind: str, uid: str, write: bool = False) -> Any:
    """Authorize the native resource before accessing translation metadata."""
    kind, uid = identity(kind, uid)
    model = {"dashboard": Dashboard, "chart": Slice, "dataset": SqlaTable}[kind]
    resource = db.session.query(model).filter(model.uuid == uid).one_or_none()
    if resource is None:
        raise LookupError("Resource not found")
    if security_manager.is_guest_user() and kind != "dashboard":
        raise PermissionError("Guests may only read an authorized dashboard bundle")
    check = {
        "dashboard": "can_access_dashboard",
        "chart": "can_access_chart",
        "dataset": "can_access_datasource",
    }[kind]
    if not getattr(security_manager, check)(resource):
        raise PermissionError("Resource access denied")
    if write:
        permission = {"dashboard": "Dashboard", "chart": "Chart", "dataset": "Dataset"}[
            kind
        ]
        if security_manager.is_guest_user() or not (
            security_manager.is_admin()
            or (
                security_manager.can_access("can_write", permission)
                and security_manager.is_owner(resource)
            )
        ):
            raise PermissionError(
                "Native resource edit permission and ownership required"
            )
    return resource


def field(
    key: str, label: str, source: Any, kind: str = "text", **binding: Any
) -> dict[str, Any]:
    """Describe a presentation field, retaining native identity bindings."""
    source = str(source or "")
    return {
        "key": key,
        "label": label,
        "source": source,
        "sourceHash": fingerprint(source),
        "kind": kind,
        **binding,
    }


def chart_fields(chart: Slice) -> list[dict[str, Any]]:
    """Discover shared chart fields and registered visualization control fields."""
    result = [
        field("title", "Chart title", chart.slice_name),
        field("description", "Chart description", chart.description),
    ]
    params = json.loads(chart.params or "{}")
    if params.get("viz_type") not in SUPPORTED:
        return result
    for key in TEXT_CONTROLS:
        if isinstance(params.get(key), str) or key in VIZ_CONTROLS[params["viz_type"]]:
            result.append(
                field(
                    "control/" + key,
                    key.replace("_", " ").title(),
                    params.get(key) or "",
                    target=key,
                )
            )
    for control in ("metric", "metrics", "metrics_b", "secondary_metrics"):
        metrics = params.get(control, [])
        if not isinstance(metrics, list):
            metrics = [metrics]
        for metric in metrics:
            if isinstance(metric, dict) and metric.get("label"):
                key = str(metric.get("optionName") or metric["label"])
                if not any(item["key"] == "metric/" + key for item in result):
                    result.append(
                        field(
                            "metric/" + key,
                            "Metric: " + metric["label"],
                            metric["label"],
                            target=metric["label"],
                        )
                    )
    for name, config in (params.get("column_config") or {}).items():
        if isinstance(config, dict):
            original = config.get("customColumnName", config.get("label"))
            if isinstance(original, str):
                result.append(
                    field(
                        "column/" + name, "Table column: " + name, original, target=name
                    )
                )
    return result


def dataset_fields(dataset: SqlaTable) -> list[dict[str, Any]]:
    """Use stable column/metric UUIDs without changing dataset definitions."""
    result = []
    for column in dataset.columns:
        prefix = "column/" + str(column.uuid)
        result.extend(
            [
                field(
                    prefix + "/label",
                    "Column: " + column.column_name,
                    column.verbose_name or column.column_name,
                    target=column.column_name,
                ),
                field(
                    prefix + "/description",
                    "Column description: " + column.column_name,
                    column.description,
                    target=column.column_name,
                ),
                field(
                    prefix + "/categories",
                    "Categories: " + column.column_name,
                    column.column_name,
                    "category",
                    target=column.column_name,
                ),
            ]
        )
    for metric in dataset.metrics:
        prefix = "metric/" + str(metric.uuid)
        result.extend(
            [
                field(
                    prefix + "/label",
                    "Metric: " + metric.metric_name,
                    metric.verbose_name or metric.metric_name,
                    target=metric.metric_name,
                ),
                field(
                    prefix + "/description",
                    "Metric description: " + metric.metric_name,
                    metric.description,
                    target=metric.metric_name,
                ),
            ]
        )
    return result


def dashboard_fields(dashboard: Dashboard) -> list[dict[str, Any]]:
    """Discover native layout/filter text and per-occurrence chart overrides."""
    result = [field("title", "Dashboard title", dashboard.dashboard_title)]
    charts = {chart.id: chart for chart in dashboard.slices}
    layout = json.loads(dashboard.position_json or "{}")
    for key, item in layout.items():
        if not isinstance(item, dict):
            continue
        meta = item.get("meta", {})
        for name in ("text", "code"):
            if isinstance(meta.get(name), str):
                result.append(
                    field(
                        f"layout/{key}/{name}",
                        f"{item.get('type', 'Layout')} {key}: {name}",
                        meta[name],
                        "markdown" if name == "code" else "text",
                    )
                )
        chart = charts.get(meta.get("chartId"))
        if chart is not None:
            for descriptor in chart_fields(chart):
                result.append(
                    {
                        **descriptor,
                        "key": f"layout/{key}/chart/{descriptor['key']}",
                        "label": chart.slice_name + " / " + descriptor["label"],
                    }
                )
        title = (meta.get("focalbi_rendering") or {}).get("title", {})
        for name in ("single", "multiple"):
            if isinstance(title.get(name), str):
                result.append(
                    field(
                        f"layout/{key}/title/{name}",
                        f"{key}: dynamic title {name}",
                        title[name],
                        "template",
                    )
                )
    for config in json.loads(dashboard.json_metadata or "{}").get(
        "native_filter_configuration", []
    ):
        for name in ("name", "description"):
            result.append(
                field(
                    f"filter/{config['id']}/{name}",
                    "Filter " + config.get("name", "") + ": " + name,
                    config.get(name, ""),
                )
            )
    return result


def fields(kind: str, resource: Any) -> list[dict[str, Any]]:
    """Dispatch by resource contract, never by business identifiers."""
    return {
        "dashboard": dashboard_fields,
        "chart": chart_fields,
        "dataset": dataset_fields,
    }[kind](resource)


def actor() -> str:
    """Record the authenticated author, never a browser-supplied identity."""
    return str(getattr(g.user, "username", "unknown"))

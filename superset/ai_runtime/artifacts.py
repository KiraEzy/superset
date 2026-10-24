# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Stable, structured BI artifacts extracted from normalized tool results."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlparse

from superset.utils import json


def extract_artifacts(  # noqa: C901 - execution state machine
    tool_name: str, call_id: str, result: dict[str, Any]
) -> list[dict[str, Any]]:  # noqa: C901 - explicit execution state machine
    """Keep chart configs and known entity references without trusting
    arbitrary HTML.
    """
    data = result.get("structuredContent")
    if result.get("isError") or not isinstance(data, dict):
        return []
    data = dict(data)
    nested = data.get("chart")
    if isinstance(nested, dict):
        for key in ("form_data", "form_data_key", "viz_type"):
            if key not in data and nested.get(key) is not None:
                data[key] = nested[key]
    if tool_name == "generate_explore_link" and data.get("url"):
        data.setdefault("explore_url", data["url"])
    artifacts = []
    for kind in ("chart", "dashboard", "dataset", "query"):
        entity = data.get(kind)
        if not isinstance(entity, dict):
            continue
        if kind == "chart" and (
            isinstance(data.get("form_data"), dict) or data.get("form_data_key")
        ):
            continue  # Prefer the renderer-ready preview/saved payload below.
        identifier = entity.get("uuid") or entity.get("id")
        if identifier is not None:
            artifacts.append(
                {
                    "type": kind,
                    "entity_id": identifier,
                    "title": entity.get("title")
                    or entity.get("slice_name")
                    or entity.get("dashboard_title"),
                    "data": {
                        **entity,
                        **(
                            {"slice_id": entity["id"]}
                            if kind == "chart" and isinstance(entity.get("id"), int)
                            else {}
                        ),
                    },
                    "call_id": call_id,
                }
            )
    if isinstance(data.get("form_data"), dict) or data.get("form_data_key"):
        chart = data.get("chart", data if tool_name == "get_chart_info" else {})
        if not isinstance(chart, dict):
            chart = {}
        payload = {
            key: data[key]
            for key in (
                "form_data",
                "form_data_key",
                "previous_form_data_key",
                "explore_url",
                "viz_type",
            )
            if key in data
        }
        payload["viz_type"] = (
            chart.get("viz_type")
            or data.get("viz_type")
            or data.get("form_data", {}).get("viz_type")
        )
        if isinstance(chart.get("id"), int):
            payload["slice_id"] = chart["id"]
        artifacts.append(
            {
                "type": "chart",
                "title": chart.get("slice_name") or "Chart preview",
                "data": payload,
                "call_id": call_id,
            }
        )
    rows = data.get("data", data.get("rows", data.get("results")))
    if isinstance(rows, list):
        artifacts.append(
            {
                "type": "table",
                "title": "Query results",
                "data": {"rows": rows, "columns": data.get("columns", [])},
                "call_id": call_id,
            }
        )
    if isinstance(data.get("sql"), str) and tool_name != "get_dataset_info":
        artifacts.append(
            {
                "type": "sql",
                "title": "SQL query",
                "data": {"sql": data["sql"]},
                "call_id": call_id,
            }
        )
    for key in ("explore_url", "dashboard_url", "chart_url"):
        url = data.get(key)
        if isinstance(url, str) and (
            url.startswith("/")
            and not url.startswith("//")
            or urlparse(url).scheme in {"http", "https"}
        ):
            artifacts.append(
                {
                    "type": "source",
                    "title": key.replace("_", " "),
                    "data": {"url": url},
                    "call_id": call_id,
                }
            )
    for artifact in artifacts:
        artifact["id"] = hashlib.sha256(
            json.dumps(artifact, sort_keys=True, default=str).encode()
        ).hexdigest()[:24]
        artifact["tool"] = tool_name
    return artifacts

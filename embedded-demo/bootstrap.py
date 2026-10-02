# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Provision a separate embedded copy of the bundled sales sample."""

from copy import deepcopy
from pathlib import Path

from superset.app import create_app
from superset.utils import json

app = create_app()
with app.app_context():
    from superset import db
    from superset.daos.dashboard import EmbeddedDashboardDAO
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    source = (
        db.session.query(Dashboard).filter_by(dashboard_title="Sales Dashboard").one()
    )
    slug = "focalbi-embedded-sales-demo"
    dashboard = db.session.query(Dashboard).filter_by(slug=slug).one_or_none()
    if dashboard is None:
        dashboard = Dashboard(
            dashboard_title="Embedded Sales Overview",
            slug=slug,
            published=True,
            owners=list(source.owners),
        )
        db.session.add(dashboard)
        db.session.flush()
        mapping = {}
        uuids = {}
        for original in source.slices:
            chart = Slice(
                slice_name=original.slice_name,
                viz_type=original.viz_type,
                datasource_id=original.datasource_id,
                datasource_type=original.datasource_type,
                owners=list(original.owners),
                description=original.description,
            )
            db.session.add(chart)
            db.session.flush()
            params = json.loads(original.params)
            params.update(
                slice_id=chart.id,
                datasource=f"{chart.datasource_id}__{chart.datasource_type}",
                dashboards=[dashboard.id],
            )
            chart.params = json.dumps(params)
            dashboard.slices.append(chart)
            mapping[original.id] = chart.id
            uuids[original.id] = str(chart.uuid)
        layout = json.loads(source.position_json)
        for item in layout.values():
            if isinstance(item, dict) and item.get("type") == "CHART":
                old_id = item["meta"]["chartId"]
                item["meta"]["chartId"] = mapping[old_id]
                item["meta"]["uuid"] = uuids[old_id]
        dashboard.position_json = json.dumps(layout)
        metadata = json.loads(source.json_metadata)
        ids = list(mapping.values())
        metadata["chart_configuration"] = {}
        metadata["global_chart_configuration"]["chartsInScope"] = ids
        filters = metadata["native_filter_configuration"]
        country = deepcopy(next(f for f in filters if f["name"] == "Country"))
        product = deepcopy(country)
        product.update(id="NATIVE_FILTER-embedded-product", name="Product line")
        product["targets"][0]["column"]["name"] = "product_line"
        metadata["native_filter_configuration"] = [
            country,
            product,
            next(f for f in filters if f["name"] == "Time Range"),
        ]
        for item in metadata["native_filter_configuration"]:
            item["chartsInScope"] = ids
        dashboard.json_metadata = json.dumps(metadata)
    dataset_ids = {s.datasource_id for s in dashboard.slices}
    if len(dataset_ids) != 1:
        raise ValueError("Demo requires all charts to use the same sales dataset")
    dataset_id = next(iter(dataset_ids))
    allowed_domains = dashboard.embedded[0].allowed_domains if dashboard.embedded else []
    embedded = EmbeddedDashboardDAO.upsert(
        dashboard, list(dict.fromkeys([*allowed_domains, "http://localhost:3100"]))
    )
    role = app.appbuilder.sm.find_role("EmbeddedViewer") or app.appbuilder.sm.add_role(
        "EmbeddedViewer"
    )
    # Explicit viewer permissions: no authoring, SQL Lab or broad datasource grants.
    required = {
        ("can_read", name)
        for name in [
            "EmbeddedDashboard",
            "Dashboard",
            "Chart",
            "Theme",
            "Annotation",
            "CssTemplate",
            "CurrentUserRestApi",
            "DashboardFilterStateRestApi",
            "DashboardPermalinkRestApi",
            "ExplorePermalinkRestApi",
        ]
    } | {
        ("can_write", "DashboardFilterStateRestApi"),
        ("can_write", "DashboardPermalinkRestApi"),
        ("can_get", "Datasource"),
        ("can_query", "Api"),
        ("can_query_form_data", "Api"),
        ("can_time_range", "Api"),
        ("can_external_metadata", "Datasource"),
        ("can_dashboard", "Superset"),
        ("can_slice", "Superset"),
        ("can_explore_json", "Superset"),
        ("can_csv", "Superset"),
        ("can_dashboard_permalink", "Superset"),
        ("can_log", "Superset"),
        ("can_view_chart_as_table", "Dashboard"),
    }
    permissions = [
        app.appbuilder.sm.find_permission_view_menu(permission, view)
        for permission, view in sorted(required)
    ]
    if any(p is None for p in permissions):
        raise ValueError(
            "Expected viewer permissions are missing; initialize Superset first"
        )
    role.permissions = permissions
    db.session.commit()
    result = {
        "dashboardUuid": str(embedded.uuid),
        "dashboardId": dashboard.id,
        "datasetId": dataset_id,
        "chartIds": sorted(s.id for s in dashboard.slices),
        "countryFilterId": country["id"]
        if "country" in locals()
        else json.loads(dashboard.json_metadata)["native_filter_configuration"][0][
            "id"
        ],
    }
    Path("/app/superset_home/focal-embed-demo.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    print("Provisioned embedded demo:", result["dashboardId"])

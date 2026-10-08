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
"""Delete only ledger-owned resources after identity and sharing checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flask import g
from superset import db, security_manager
from superset.app import create_app


def authenticate_cleanup(username: str, selected_post: int | None) -> None:
    """Use a real assigned post for ordinary ownership and access checks."""
    user = security_manager.find_user(username=username)
    if not user:
        raise ValueError("Cleanup user not found")
    g.user = user
    if hasattr(security_manager, "set_active_post"):
        posts = security_manager.get_user_posts(user)
        post_id = selected_post or (posts[0].id if len(posts) == 1 else None)
        if post_id is None:
            raise ValueError("Choose an assigned active post with --post-id")
        security_manager.set_active_post(user, post_id)


def validate_resources(
    resources: list[dict],
    datasets: list[dict],
    dashboard_ids: set[int],
    chart_ids: set[int],
) -> None:
    """Validate the entire deletion set before making any mutation."""
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    for item in resources:
        dashboard = item.get("dashboard")
        if dashboard and (model := db.session.get(Dashboard, dashboard["id"])):
            if (
                model.dashboard_title != dashboard["name"]
                or {s.id for s in model.slices} - chart_ids
            ):
                raise ValueError(
                    "Dashboard identity or membership changed; refusing cleanup"
                )
            security_manager.raise_for_ownership(model)
        for chart in item["charts"]:
            if model := db.session.get(Slice, chart["id"]):
                if (
                    model.slice_name != chart["name"]
                    or {d.id for d in model.dashboards} - dashboard_ids
                ):
                    raise ValueError(
                        "Chart identity changed or it is shared outside the module"
                    )
                security_manager.raise_for_ownership(model)
    validate_datasets(datasets, chart_ids)


def validate_datasets(datasets: list[dict], chart_ids: set[int]) -> None:
    """Refuse deletion of renamed datasets or datasets shared beyond the ledger."""
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.slice import Slice

    for dataset in datasets:
        if model := db.session.get(SqlaTable, dataset["id"]):
            linked = (
                db.session.query(Slice)
                .filter_by(datasource_id=model.id, datasource_type="table")
                .all()
            )
            if (
                model.table_name != dataset["name"]
                or {s.id for s in linked} - chart_ids
            ):
                raise ValueError(
                    "Dataset identity changed or is shared outside the deletion set"
                )
            security_manager.raise_for_ownership(model)


def delete_resources(
    dashboard_ids: set[int], chart_ids: set[int], datasets: list[dict]
) -> None:
    """Use native deletion commands after identity/sharing validation."""
    from superset.commands.chart.delete import DeleteChartCommand
    from superset.commands.dashboard.delete import DeleteDashboardCommand
    from superset.commands.dataset.delete import DeleteDatasetCommand
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    for ident in dashboard_ids:
        if db.session.get(Dashboard, ident):
            DeleteDashboardCommand([ident]).run()
    for ident in chart_ids:
        if db.session.get(Slice, ident):
            DeleteChartCommand([ident]).run()
    for dataset in datasets:
        if db.session.get(SqlaTable, dataset["id"]):
            DeleteDatasetCommand([dataset["id"]]).run()


def main() -> None:
    """Validate recorded ownership, delete the selected resources and emit a receipt."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--key")
    parser.add_argument("--post-id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    path = args.ledger
    ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    if ledger["owner"] != "focalbi.rendering":
        raise ValueError("Unrecognized resource ownership ledger")
    resources = [
        item for item in ledger["resources"] if not args.key or item["key"] == args.key
    ]
    dashboard_ids = {
        item["dashboard"]["id"] for item in resources if item.get("dashboard")
    }
    chart_ids = {chart["id"] for item in resources for chart in item["charts"]}
    retained = [item for item in ledger["resources"] if item not in resources]
    selected_datasets = {
        ident
        for resource in resources
        for ident in resource.get("dataset_ids", [resource["dataset_id"]])
    }
    retained_datasets = {
        ident
        for resource in retained
        for ident in resource.get("dataset_ids", [resource["dataset_id"]])
    }
    datasets = [
        item
        for item in ledger.get("datasets", [])
        if item["id"] in selected_datasets and item["id"] not in retained_datasets
    ]
    app = create_app()
    with app.app_context():
        with app.test_request_context():
            authenticate_cleanup(args.username, args.post_id)
            validate_resources(resources, datasets, dashboard_ids, chart_ids)
            print(
                json.dumps(
                    {
                        "dashboards": sorted(dashboard_ids),
                        "charts": sorted(chart_ids),
                        "datasets": [d["id"] for d in datasets],
                        "dry_run": args.dry_run,
                    }
                )
            )
            if args.dry_run:
                return
            delete_resources(dashboard_ids, chart_ids, datasets)
    ledger["resources"] = retained
    ledger["datasets"] = [
        item for item in ledger.get("datasets", []) if item not in datasets
    ]
    # Cleanup inputs are copied to temporary container files. The host uninstall
    # tool persists this receipt only after successful native deletion.
    print("FOCALBI_CLEANUP_LEDGER=" + json.dumps(ledger))


if __name__ == "__main__":
    main()

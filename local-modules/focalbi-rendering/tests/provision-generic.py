# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
"""Provision unrelated native test resources using configured Codex MCP only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from codex_mcp import CodexMCP  # noqa: E402 -- import the module's operator helper

SQL = """SELECT * FROM (VALUES
('Central', DATE '2024-01-01', 'Young', 'Owner', 'Chinese', 'Small', 40::numeric),
('Central', DATE '2024-01-02', 'Adult', 'Renter', 'English', 'Large', 60::numeric),
('North', DATE '2025-01-01', 'Young', 'Renter', 'Chinese', 'Large', 20::numeric),
('North', DATE '2025-01-02', 'Senior', 'Owner', 'Chinese', 'Small', 30::numeric),
('West', DATE '2026-01-01', 'Adult', 'Owner', 'English', 'Small', 50::numeric),
('West', DATE '2026-01-02', 'Senior', 'Renter', 'Chinese', 'Large', 10::numeric)
) AS demo(district, surveyed_on, age_band, tenure,
language_group, household_group, residents)"""


def main() -> None:
    """Create the fixture and record ownership immediately after each mutation."""
    path = ROOT / ".runtime/resources.json"
    ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    key = "native-demographic-test"
    if any(item["key"] == key for item in ledger["resources"]):
        raise ValueError(
            "Fixture already recorded; reuse it or clean up its ledger key"
        )
    client = CodexMCP()
    try:
        dataset = client.call(
            "create_virtual_dataset",
            {
                "database_id": 1,
                "dataset_name": (
                    "Rendering compatibility - synthetic demographic sample"
                ),
                "schema": "public",
                "description": "Synthetic test data, not actual census statistics.",
                "sql": SQL,
            },
        )
        resource = {"key": key, "dataset_id": dataset["id"], "charts": []}
        ledger["resources"].append(resource)
        ledger["datasets"].append(
            {"id": dataset["id"], "name": dataset["dataset_name"]}
        )

        def persist() -> None:
            """Persist cleanup identities without storing credentials."""
            path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

        persist()
        for column in [
            "district",
            "age_band",
            "tenure",
            "language_group",
            "household_group",
        ]:
            result = client.call(
                "generate_chart",
                {
                    "dataset_id": dataset["id"],
                    "chart_name": f"Synthetic demographic sample - {column}",
                    "config": {
                        "chart_type": "pie",
                        "dimension": {"name": column},
                        "metric": {
                            "name": "residents",
                            "aggregate": "SUM",
                            "label": "Residents",
                        },
                    },
                    "save_chart": True,
                    "generate_preview": False,
                },
            )
            resource["charts"].append(
                {"id": result["chart"]["id"], "name": result["chart"]["slice_name"]}
            )
            persist()
        result = client.call(
            "generate_dashboard",
            {
                "chart_ids": [chart["id"] for chart in resource["charts"]],
                "dashboard_title": (
                    "Rendering compatibility | Synthetic demographic sample"
                ),
                "published": True,
                "description": (
                    "Synthetic native rendering test; not actual census data."
                ),
            },
        )
        resource["dashboard"] = {
            "id": result["dashboard"]["id"],
            "name": result["dashboard"]["dashboard_title"],
        }
        persist()
        client.call(
            "configure_dashboard",
            {
                "dashboard_id": resource["dashboard"]["id"],
                "filters": [
                    {
                        "name": "District",
                        "column": "district",
                        "dataset_id": dataset["id"],
                        "default_values": ["Central"],
                    }
                ],
                "overview_layout": True,
                "introduction": (
                    "## Synthetic native rendering compatibility\n"
                    "Not actual census statistics."
                ),
            },
        )
        (ROOT / ".runtime/generic-test.json").write_text(
            json.dumps(resource), encoding="utf-8"
        )
        print(result["dashboard_url"])
    finally:
        client.close()


if __name__ == "__main__":
    main()

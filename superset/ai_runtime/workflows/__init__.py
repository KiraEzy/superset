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
"""Versioned, instruction-only BI workflows; these never grant tool permissions."""

from __future__ import annotations

from typing import Any

WORKFLOWS: dict[str, dict[str, Any]] = {
    "analyze_data": {
        "id": "analyze_data",
        "name": "Analyze data",
        "version": 1,
        "description": (
            "Investigate a BI question using inspected datasets and sourced results."
        ),
        "instructions": (
            "Clarify the business question, grain, time window and c"
            "omparison. Inspect database/dataset schemas before quer"
            "ying. Use existing approved read tools; SQL execution n"
            "eeds argument-specific approval. Report evidence, filte"
            "rs, units, nulls and limitations. Never invent query re"
            "sults."
        ),
    },
    "create_chart": {
        "id": "create_chart",
        "name": "Create chart",
        "version": 1,
        "description": "Build and revise a chart preview before any persistent save.",
        "instructions": (
            "Inspect the dataset and chart-type schema. Select meani"
            "ngful dimensions, metrics, aggregation and filters. Pre"
            "view first with save_chart=false. Preserve form_data an"
            "d form_data_key as artifacts. Save when directly reques"
            "ted within the user's action scope; ambiguous saves req"
            "uire exact approval. Return the tool-provided Explore o"
            "r chart URL."
        ),
    },
    "build_dashboard": {
        "id": "build_dashboard",
        "name": "Build dashboard",
        "version": 1,
        "description": "Plan and assemble a coherent dashboard with approved changes.",
        "instructions": (
            "Establish audience, business decisions and shared filte"
            "rs. Reuse relevant charts where appropriate. Preview ch"
            "arts and explain layout before persistent operations. E"
            "xecute explicitly requested changes within scope; obtai"
            "n exact approval for ambiguous, destructive or access-c"
            "hanging actions. Verify returned identifiers and link t"
            "he resulting dashboard."
        ),
    },
    "explain_asset": {
        "id": "explain_asset",
        "name": "Explain an asset",
        "version": 1,
        "description": (
            "Explain an existing chart, dashboard or dataset from inspected metadata."
        ),
        "instructions": (
            "Resolve the validated resource ID and inspect metadata "
            "and data lineage using read tools. Explain metrics, dim"
            "ensions, time grain, filters and refresh limitations. D"
            "istinguish inspected evidence from inference. Ask for a"
            " resource identifier when ambiguous. Never modify the a"
            "sset during explanation."
        ),
    },
    "investigate_metric": {
        "id": "investigate_metric",
        "name": "Investigate a metric change",
        "version": 1,
        "description": (
            "Compare consistent periods and validate the drivers of a metric movement."
        ),
        "instructions": (
            "Resolve the metric definition, grain, timezone, filters"
            " and comparison periods. Inspect freshness and missingn"
            "ess before interpreting a change. Compare like-for-like"
            " totals and segment contributions. Distinguish measured"
            " drivers from hypotheses, cite query/chart evidence and"
            " describe limitations. Do not modify saved BI resources"
            " while investigating."
        ),
    },
}


for workflow_id, workflow in WORKFLOWS.items():
    workflow["triggers"] = [workflow_id]
    workflow["required_capabilities"] = ["tools"]
    workflow["outputs"] = ["sourced_answer", "artifact_references"]


def workflow_catalog() -> list[dict[str, Any]]:
    """Return public metadata without granting capabilities or exposing prompts."""
    return [
        {key: value for key, value in item.items() if key != "instructions"}
        for item in WORKFLOWS.values()
    ]


def workflow_instructions(ids: list[str]) -> str:
    """Resolve only trusted workflow manifests selected by ID."""
    unknown = set(ids) - WORKFLOWS.keys()
    if unknown:
        from superset.ai_runtime.contracts import (
            AiRuntimeError,  # pylint: disable=import-outside-toplevel
        )

        raise AiRuntimeError("Unknown BI workflow", code="invalid_workflow")
    return "\n".join(WORKFLOWS[item]["instructions"] for item in ids)

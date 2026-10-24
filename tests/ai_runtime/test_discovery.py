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
"""Discovery progress, corrective dispatch and scoped resource memory."""

import copy
import importlib

import test_engine as runtime

from superset.utils import json

discovery = importlib.import_module(f"{runtime.PACKAGE}.discovery")


def target(name="list_datasets", connection="c"):
    tool = runtime.tool(name, focal=True)
    tool.connection["id"] = connection
    tool.schema = {"type": "object", "properties": {"request": {"type": "object"}}}
    return tool


def result(records, **metadata):
    return {"structuredContent": {"datasets": records, **metadata}, "isError": False}


def test_scope_ignores_projection_pagination_and_sort_but_not_filters_or_connection():
    base = {"request": {"search": "geography", "page": 1, "select_columns": ["id"]}}
    altered = {"request": {"search": "geography", "page": 4, "order_column": "id"}}
    assert discovery.scope("list_datasets", base, "a") == discovery.scope(
        "list_datasets", altered, "a"
    )
    assert discovery.scope("list_datasets", base, "a") != discovery.scope(
        "list_datasets", base, "b"
    )
    assert discovery.scope("list_datasets", base, "a") != discovery.scope(
        "list_charts", base, "a"
    )
    altered["request"]["search"] = "other"
    assert discovery.scope("list_datasets", base, "a") != discovery.scope(
        "list_datasets", altered, "a"
    )


def test_pages_projection_metadata_and_refresh_are_distinct():
    state = discovery.fresh_state()
    tool = target()
    args = {"request": {"search": "geography", "select_columns": ["id", "table_name"]}}
    value = result(
        [{"id": 28, "table_name": "geography"}], total_count=34, has_next=True
    )
    assert discovery.observe(state, tool, args, value, "first")
    assert discovery.duplicate(state, tool, args) == "first"
    more = copy.deepcopy(args)
    more["request"]["select_columns"].append("description")
    assert discovery.duplicate(state, tool, more) is None
    assert discovery.observe(
        state,
        tool,
        more,
        result([{"id": 28, "table_name": "geography", "description": "New detail"}]),
        "detail",
    )
    page = copy.deepcopy(args)
    page["request"]["page"] = 2
    assert discovery.duplicate(state, tool, page) is None
    refresh = copy.deepcopy(args)
    refresh["request"]["force_refresh"] = True
    assert discovery.duplicate(state, tool, refresh) is None
    assert not discovery.observe(
        state,
        tool,
        more,
        result(
            [
                {
                    "id": 28,
                    "table_name": "geography",
                    "description": "New detail",
                    "changed_on": "later",
                }
            ]
        ),
        "same",
    )


def test_exact_matches_have_schema_valid_inspection_hints_and_remain_ambiguous():
    state = discovery.fresh_state()
    listing = target()
    args = {"request": {"search": "hk_census_2021_geography", "page": 4}}
    discovery.observe(
        state,
        listing,
        args,
        result(
            [
                {
                    "id": 28,
                    "table_name": "hk_census_2021_geography",
                    "schema": "public",
                },
                {"id": 29, "table_name": "hk_census_2021_geography", "schema": "other"},
            ]
        ),
        "page4",
    )
    inspect = target("get_dataset_info")
    inspect.name = "namespaced_inspection"
    inspect.schema["properties"]["request"] = {
        "type": "object",
        "properties": {"identifier": {"type": "integer"}},
        "required": ["identifier"],
        "additionalProperties": False,
    }
    observed = discovery.observation(state, [inspect])["runtime_discovery"]
    assert observed["ambiguous"]
    assert observed["suggested_next_steps"][0]["arguments"] == {
        "request": {"identifier": 28}
    }
    assert observed["suggested_next_steps"][0]["tool"] == "namespaced_inspection"
    discovery.inspect_dataset(state, inspect, {"request": {"identifier": 28}})
    assert discovery.matches(state)[0]["schema_inspected"]
    assert not discovery.matches(state)[1]["schema_inspected"]


def test_evidence_guard_allows_new_ranges_and_paths():
    state = discovery.fresh_state()
    args = {"call_id": "source", "path": ["datasets"], "offset": 0, "limit": 10}
    discovery.observe_read(
        state, args, {"data": [1, 2, 3], "offset": 0, "total": 8}, "read1"
    )
    assert discovery.read_duplicate(state, args) == "source"
    assert discovery.read_duplicate(state, {**args, "offset": 3}) is None
    assert discovery.read_duplicate(state, {**args, "path": ["columns"]}) is None


def test_parallel_duplicate_is_intercepted_but_schema_and_chart_work_remain():
    checkpoints = []
    listing = target()
    inspection = target("get_dataset_info")
    chart = target("generate_chart")

    class Pool(runtime.Pool):
        async def call(self, tool, arguments):
            await super().call(tool, arguments)
            if tool.original_name == "list_datasets":
                return result([{"id": 28, "table_name": "hk_census_2021_geography"}])
            return {"isError": False, "structuredContent": {"id": 28, "columns": []}}

    args = {"request": {"search": "hk_census_2021_geography"}}
    provider = runtime.Provider(
        [
            runtime.contracts.Generation(
                calls=[
                    runtime.call("list_datasets", "a", args),
                    runtime.call("list_datasets", "b", args),
                ]
            ),
            runtime.contracts.Generation(
                calls=[
                    runtime.call(
                        "get_dataset_info", "inspect", {"request": {"identifier": 28}}
                    )
                ]
            ),
            runtime.contracts.Generation(
                calls=[
                    runtime.call(
                        "generate_chart", "chart", {"request": {"dataset_id": 28}}
                    )
                ]
            ),
            runtime.contracts.Generation(content="Preview ready"),
        ]
    )
    pool = Pool([listing, inspection, chart], checkpoints)
    outcome = runtime.run(
        {
            "_provider": provider,
            "_mcp_pool": pool,
            "input_text": "use hk_census_2021_geography",
        },
        checkpoints,
    )
    assert outcome["status"] == "completed"
    assert [name for name, _ in pool.invocations] == [
        "list_datasets",
        "get_dataset_info",
        "generate_chart",
    ]
    cp = outcome["checkpoint"]
    assert cp["calls"]["b"]["result"]["external_dispatch"] is False
    assert cp["discovery"]["interventions"] == 1
    assert discovery.matches(cp["discovery"])[0]["schema_inspected"]
    assert "hk_census_2021_geography" in json.dumps(provider.requests[-1])


def test_checkpoint_recovery_hydrates_without_replaying_historical_calls():
    checkpoints = []
    listing = target()
    args = {"request": {"search": "geography", "select_columns": ["id", "table_name"]}}
    prior = runtime.call("list_datasets", "prior", args)
    duplicate = runtime.call("list_datasets", "retry", args)
    provider = runtime.Provider(
        [runtime.contracts.Generation(content="Use recorded dataset")]
    )
    pool = runtime.Pool([listing], checkpoints)
    cp = {
        "initialized": True,
        "messages": [
            {"role": "user", "content": "Find geography"},
            {"role": "assistant", "tool_calls": [prior]},
            {
                "role": "tool",
                "tool_call_id": "prior",
                "content": json.dumps(result([{"id": 28, "table_name": "geography"}])),
            },
            {"role": "assistant", "tool_calls": [duplicate]},
        ],
        "pending_calls": [duplicate],
    }
    outcome = runtime.run(
        {"checkpoint": cp, "_provider": provider, "_mcp_pool": pool}, checkpoints
    )
    assert outcome["status"] == "completed"
    assert pool.invocations == []
    assert outcome["checkpoint"]["calls"]["retry"]["result"]["source"] == "chat_runtime"


def test_three_blocked_parallel_generations_count_once_each():
    checkpoints = []
    listing = target()
    args = {"request": {"select_columns": ["id"]}}
    provider = runtime.Provider(
        [
            runtime.contracts.Generation(
                calls=[runtime.call("list_datasets", "first", args)]
            ),
            *[
                runtime.contracts.Generation(
                    calls=[
                        runtime.call("list_datasets", f"repeat-{n}-{j}", args)
                        for j in range(3)
                    ]
                )
                for n in range(3)
            ],
            runtime.contracts.Generation(content="Partial answer"),
        ]
    )
    pool = runtime.Pool([listing], checkpoints)
    outcome = runtime.run({"_provider": provider, "_mcp_pool": pool}, checkpoints)
    assert outcome["status"] == "completed"
    assert len(pool.invocations) == 1
    assert outcome["checkpoint"]["discovery"]["blocked_generations"] == 3
    assert outcome["checkpoint"]["discovery"]["interventions"] == 9


def test_context_overlap_keeps_new_fields_across_projection_changes():
    context = importlib.import_module(f"{runtime.PACKAGE}.context")
    messages = [{"role": "user", "content": "Find geography"}]
    for n, columns in enumerate(
        [
            ["id", "table_name"],
            ["id", "table_name", "description"],
            ["table_name", "id"],
        ]
    ):
        record = {"id": 28, "table_name": "geography"}
        if "description" in columns:
            record["description"] = "District boundaries"
        messages += [
            {
                "role": "assistant",
                "tool_calls": [
                    runtime.call(
                        "list_datasets",
                        str(n),
                        {"request": {"select_columns": columns}},
                    )
                ],
            },
            {
                "role": "tool",
                "tool_call_id": str(n),
                "content": json.dumps(result([record])),
            },
        ]
    view = context.model_context(messages)
    rows = [json.loads(m["content"]) for m in view if m.get("role") == "tool"]
    assert "District boundaries" in json.dumps(rows[1])
    assert rows[2]["result"]["datasets"] == []
    assert rows[2]["result"]["overlap"]["omitted_unchanged_records"] == 1


def test_unresolved_lookup_exposes_next_page_and_natural_name_matches():
    tracker = discovery.fresh_state()
    listing = target()
    args = {"request": {"search": "census", "page": 1, "page_size": 25}}
    discovery.observe(
        tracker,
        listing,
        args,
        result([{"id": 1, "table_name": "Other"}], page=1, page_size=25, has_next=True),
        "first",
    )
    hint = discovery.observation(tracker, [listing])["runtime_discovery"][
        "suggested_next_steps"
    ][0]
    assert hint["arguments"]["request"]["page"] == 2
    assert hint["arguments"]["request"]["page_size"] == 25
    discovery.observe(
        tracker,
        listing,
        hint["arguments"],
        result(
            [{"id": 28, "table_name": "hk_census_2021_geography"}],
            page=2,
            has_next=False,
        ),
        "second",
        "use hk census 2021 geography to create charts",
    )
    assert discovery.matches(tracker)[0]["dataset_id"] == 28


def test_context_pressure_retains_inspection_then_chart_tools(monkeypatch):
    original = runtime.engine.model_context

    def pressured(messages, **kwargs):
        if any(t["function"]["name"] == "unrelated_tool" for t in kwargs["tools"]):
            raise runtime.contracts.AiRuntimeError(
                "Full tool set exceeds budget", code="context_budget"
            )
        return original(messages, **kwargs)

    monkeypatch.setattr(runtime.engine, "model_context", pressured)
    checkpoints = []
    listing, inspect, chart = (
        target(),
        target("get_dataset_info"),
        target("generate_chart"),
    )
    tracker = discovery.fresh_state()
    discovery.observe(
        tracker,
        listing,
        {"request": {"search": "geography"}},
        result([{"id": 28, "table_name": "geography"}]),
        "recorded",
    )

    class Provider(runtime.Provider):
        async def generate(self, messages, tools, **kwargs):
            names = [t["function"]["name"] for t in tools]
            assert "unrelated_tool" not in names
            assert "get_dataset_info" in names
            assert "geography" in json.dumps(messages)
            if self.requests:
                assert "generate_chart" in names
                assert "get_chart_data" in names
            return await super().generate(messages, tools, **kwargs)

    provider = Provider(
        [
            runtime.contracts.Generation(
                calls=[
                    runtime.call(
                        "get_dataset_info", "inspect", {"request": {"identifier": 28}}
                    )
                ]
            ),
            runtime.contracts.Generation(
                calls=[
                    runtime.call(
                        "generate_chart", "chart", {"request": {"dataset_id": 28}}
                    )
                ]
            ),
            runtime.contracts.Generation(content="Preview ready"),
        ]
    )
    pool = runtime.Pool(
        [listing, inspect, chart, target("get_chart_data"), target("unrelated_tool")],
        checkpoints,
    )
    outcome = runtime.run(
        {
            "checkpoint": {"discovery": tracker},
            "_provider": provider,
            "_mcp_pool": pool,
        },
        checkpoints,
    )
    assert outcome["status"] == "completed"
    assert outcome["checkpoint"]["discovery_recovery"] == "focused_tools"
    assert not outcome["checkpoint"].get("discovery_exhausted")


def test_smaller_page_inside_covered_range_does_not_repeat_discovery():
    tracker = discovery.fresh_state()
    listing = target()
    args = {"request": {"search": "census", "page_size": 25, "select_columns": ["id"]}}
    discovery.observe(
        tracker,
        listing,
        args,
        result([{"id": n} for n in range(25)], total_count=34),
        "wide",
    )
    smaller = {
        "request": {
            "search": "census",
            "page": 2,
            "page_size": 10,
            "select_columns": ["id"],
        }
    }
    assert discovery.duplicate(tracker, listing, smaller) == "wide"
    smaller["request"]["page"] = 3
    assert discovery.duplicate(tracker, listing, smaller) is None
    smaller["request"]["page"] = 1
    smaller["request"]["select_columns"].append("description")
    assert discovery.duplicate(tracker, listing, smaller) is None


def test_recorded_server_page_size_controls_coverage_and_refresh_invalidates_it():
    tracker = discovery.fresh_state()
    listing = target()
    args = {"request": {"search": "census", "page": 2, "select_columns": ["id"]}}
    discovery.observe(
        tracker,
        listing,
        args,
        result(
            [{"id": n} for n in range(25, 34)], page=2, page_size=25, total_count=34
        ),
        "actual",
    )
    page = {
        "request": {
            "search": "census",
            "page": 4,
            "page_size": 10,
            "select_columns": ["id"],
        }
    }
    assert discovery.duplicate(tracker, listing, page) == "actual"
    refresh = {
        "request": {
            "search": "census",
            "force_refresh": True,
            "page": 1,
            "page_size": 10,
            "select_columns": ["id"],
        }
    }
    discovery.observe(
        tracker,
        listing,
        refresh,
        result([{"id": 1}], page=1, page_size=10, total_count=1),
        "refreshed",
    )
    assert discovery.duplicate(tracker, listing, page) is None


def test_external_cursor_and_non_object_requests_keep_original_semantics():
    tracker = discovery.fresh_state()
    listing = target()
    listing.connection["is_focal"] = False
    args = {"request": {"page": "cursor-a", "select_columns": "id,name"}}
    discovery.observe(tracker, listing, args, result([{"id": 1}]), "cursor")
    assert discovery.duplicate(tracker, listing, args) == "cursor"
    assert (
        discovery.duplicate(tracker, listing, {"request": {"page": "cursor-b"}}) is None
    )
    assert discovery.duplicate(tracker, listing, {"request": ["a", "b"]}) is None
    assert not discovery.observe(
        tracker, listing, {"request": ["a", "b"]}, result([]), "array"
    )

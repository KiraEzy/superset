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
"""Regression tests for bounded views over a lossless execution ledger."""

import copy

import pytest
import test_engine

from superset.utils import json

context = __import__(f"{test_engine.PACKAGE}.context", fromlist=["model_context"])


def interaction(index, size=12000):
    return [
        {
            "role": "assistant",
            "content": "Inspect age ordering",
            "tool_calls": [
                {
                    "id": f"call-{index}",
                    "function": {
                        "name": "inspect",
                        "arguments": json.dumps({"id": index}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": f"call-{index}",
            "content": json.dumps(
                {
                    "structuredContent": {
                        "dataset_id": 42,
                        "filters": {"year": 2025},
                        "rows": [{"id": n, "value": "x" * size} for n in range(10)],
                    },
                    "raw": "duplicate" * size,
                }
            ),
        },
    ]


def assert_pairs(view):
    pending = set()
    for message in view:
        if message.get("tool_calls"):
            assert not pending
            pending = {c["id"] for c in message["tool_calls"]}
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
    assert not pending


def test_regression_repeated_guidance_and_large_current_turn():
    messages = [{"role": "system", "content": "Policy"}]
    guidance = [{"connection": "focalbi", "instructions": "x" * 13000}]
    for turn in range(3):
        messages += [
            {"role": "user", "content": f"Request {turn}"},
            {"role": "user", "content": context.GUIDANCE_PREFIX + json.dumps(guidance)},
        ]
        for n in range(10):
            messages += interaction(turn * 10 + n)
    original = copy.deepcopy(messages)
    checkpoint = {}
    view = context.model_context(messages, max_chars=30000, checkpoint=checkpoint)
    assert len(context.serialized(view)) <= 30000
    assert (
        sum(str(m.get("content", "")).startswith(context.GUIDANCE_PREFIX) for m in view)
        == 1
    )
    assert {"role": "user", "content": "Request 2"} in view
    assert_pairs(view)
    assert messages == original
    assert checkpoint["version"] == 1
    assert checkpoint["summaries"]
    assert (
        context.model_context(messages, max_chars=30000, checkpoint=checkpoint) == view
    )


def test_identical_result_deduplication_does_not_hide_changed_data():
    messages = interaction(1, 20)
    messages += copy.deepcopy(messages)
    messages[2]["tool_calls"][0]["id"] = "again"
    messages[3]["tool_call_id"] = "again"
    # Same normalized arguments, same exact result, different call identity.
    view = context.model_context(messages)
    assert json.loads(view[3]["content"])["duplicate_of"] == "call-1"
    messages[3]["content"] = json.dumps({"value": "fresh data"})
    assert "duplicate_of" not in context.model_context(messages)[3]["content"]
    assert len(messages) == 4  # No execution or canonical transcript is deduplicated.


def test_schema_tokens_and_image_costs_count_against_budget():
    messages = [{"role": "user", "content": "Keep this exact request"}]
    with pytest.raises(test_engine.contracts.AiRuntimeError, match="tool schemas"):
        context.model_context(messages, max_tokens=100, tools=[{"schema": "x" * 1000}])
    image = [
        {"role": "user", "content": [{"type": "image_ref", "image_id": "private"}]}
    ]
    assert context.estimate_tokens(image) >= 4096


def test_current_request_and_inflight_calls_are_not_silently_cut():
    messages = [{"role": "user", "content": "x" * 10000}]
    with pytest.raises(test_engine.contracts.AiRuntimeError):
        context.model_context(messages, max_chars=1000)
    inflight = interaction(1)[:1]
    with pytest.raises(test_engine.contracts.AiRuntimeError):
        context.model_context(inflight, max_chars=30)


def test_long_history_bounds_rolling_memory_without_restoring_dropped_groups():
    messages = [{"role": "system", "content": "Policy"}]
    for n in range(90):
        messages += [{"role": "user", "content": f"Past request {n}" + "x" * 3000}]
        messages += interaction(n, 20)
    messages += [
        {"role": "user", "content": "Continue the latest preview; do not save"}
    ]
    view = context.model_context(messages, max_chars=8000, checkpoint={})
    assert len(context.serialized(view)) <= 8000
    assert view[-1] == messages[-1]
    assert_pairs(view)
    memory = next(
        json.loads(m["content"])
        for m in view
        if '"kind":"conversation_memory"' in str(m.get("content"))
    )
    assert memory["earlier_source_ranges"]


def test_summary_never_exposes_private_reasoning_and_invalidates_changed_source():
    messages = [
        {"role": "user", "content": "Original"},
        {
            "role": "assistant",
            "content": "public " * 3000,
            "reasoning_content": "SECRET_REASONING",
        },
        {"role": "user", "content": "Current"},
    ]
    checkpoint = {}
    view = context.model_context(messages, max_chars=3000, checkpoint=checkpoint)
    assert "SECRET_REASONING" not in context.serialized(view)
    before = copy.deepcopy(checkpoint["summaries"])
    messages[1]["content"] = "Changed " * 3000
    context.model_context(messages, max_chars=3000, checkpoint=checkpoint)
    assert before.keys() != checkpoint["summaries"].keys()


def test_guidance_is_request_scoped_and_read_evidence_recovers_exact_user_text():
    checkpoints = []
    provider = test_engine.Provider(
        [
            test_engine.contracts.Generation(
                calls=[
                    test_engine.call(
                        "read_evidence",
                        args={
                            "call_id": "message:1",
                            "path": ["content"],
                            "limit": 100,
                        },
                    )
                ]
            ),
            test_engine.contracts.Generation(content="Recovered"),
        ]
    )
    pool = test_engine.Pool([], checkpoints)
    pool.instructions = [{"text": "current guidance"}]
    result = test_engine.run(
        {
            "messages": [
                {"role": "user", "content": "Retain filters year=2025; no saves"}
            ],
            "input_text": "Continue",
            "_provider": provider,
            "_mcp_pool": pool,
        },
        checkpoints,
    )
    assert result["status"] == "completed"
    assert not any(
        str(m.get("content", "")).startswith(context.GUIDANCE_PREFIX)
        for m in result["messages"]
    )
    evidence = next(
        m for m in provider.requests[1] if m.get("tool_call_id") == "call-1"
    )
    assert "year=2025" in evidence["content"]
    assert not pool.invocations


def test_older_images_remain_available_after_compaction():
    messages = [
        {
            "role": "user",
            "content": [{"type": "image_ref", "image_id": "private-image"}],
        }
    ]
    messages += interaction(1)
    messages += [{"role": "user", "content": "What was shown in that image?"}]
    view = context.model_context(messages, max_chars=4000)
    assert messages[0] in view
    assert_pairs(view)


def test_model_specific_limits_are_snapshotted_from_operator_configuration():
    from importlib import import_module

    from flask import Flask

    settings = import_module(f"{test_engine.PACKAGE}.settings")
    app = Flask(__name__)
    app.config["AI_RUNTIME_MODEL_CONTEXT_LIMITS"] = {
        "small": {
            "context_window_tokens": 8192,
            "response_tokens": 1024,
            "tool_result_tokens": 1024,
        }
    }
    with app.app_context():
        assert settings.limits("small")["context_window_tokens"] == 8192
        assert settings.limits("other")["context_window_tokens"] == 32768


def test_discovery_page_keeps_ids_and_names_beyond_first_eight_results():
    datasets = [
        {
            "id": n,
            "table_name": f"Dataset {n}",
            "description": "large description " * 1000,
        }
        for n in range(32)
    ]
    result = {
        "role": "tool",
        "tool_call_id": "discovery",
        "content": json.dumps(
            {"structuredContent": {"datasets": datasets, "has_next": False}}
        ),
    }
    view = context.model_context([result])
    assert "Dataset 31" in view[0]["content"]
    assert len(view[0]["content"]) < 5000


def test_latest_complete_result_stays_actionable_under_compaction():
    messages = [{"role": "user", "content": "Inspect data"}]
    for n in range(30):
        messages += interaction(n, 20)
    messages[-1]["content"] = json.dumps(
        {"dataset_id": 31, "population_metric": "total_population"}
    )
    view = context.model_context(messages, max_chars=8000)
    assert messages[-1] in view
    assert_pairs(view)


def test_large_dataset_metadata_keeps_actionable_columns_and_metrics():
    columns = [
        {"column_name": f"column_{n}", "type": "FLOAT", "description": "x" * 10000}
        for n in range(20)
    ]
    columns[13]["column_name"] = "population"
    result = {
        "isError": False,
        "structuredContent": {
            "id": 31,
            "columns": columns,
            "metrics": [{"metric_name": "count", "expression": "COUNT(*)"}],
            "sql": "x" * 10000,
        },
    }
    view = context.model_context(
        [{"role": "tool", "tool_call_id": "schema", "content": json.dumps(result)}]
    )
    assert "population" in view[0]["content"]
    assert "COUNT(*)" in view[0]["content"]
    assert len(view[0]["content"]) < 5000


def test_official_deepseek_budget_does_not_apply_to_custom_endpoints():
    from importlib import import_module

    from flask import Flask

    settings = import_module(f"{test_engine.PACKAGE}.settings")
    with Flask(__name__).app_context():
        assert (
            settings.limits(
                "deepseek-v4-flash", {"llmApiBaseUrl": "https://api.deepseek.com/v1"}
            )["context_window_tokens"]
            == 128000
        )
        assert (
            settings.limits(
                "deepseek-v4-flash", {"llmApiBaseUrl": "https://custom.invalid/v1"}
            )["context_window_tokens"]
            == 32768
        )


def test_overlapping_text_backed_pages_keep_new_and_changed_records():
    messages = [{"role": "user", "content": "What datasets can I use?"}]
    for page, ids in enumerate(([1, 2], [2, 3], [2]), 1):
        records = [
            {"id": n, "table_name": f"Dataset {n}", "description": "x" * 15000}
            for n in ids
        ]
        if page == 3:
            records[0]["table_name"] = "Renamed dataset"
        messages += [
            {
                "role": "assistant",
                "tool_calls": [
                    test_engine.call(
                        "server__list_datasets",
                        f"page-{page}",
                        {
                            "request": {
                                "page": page,
                                "page_size": 2,
                                "filter": "permitted",
                            }
                        },
                    )
                ],
            },
            {
                "role": "tool",
                "tool_call_id": f"page-{page}",
                "content": json.dumps(
                    {
                        "isError": False,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"datasets": records, "page": page}),
                            }
                        ],
                        "structuredContent": None,
                    }
                ),
            },
        ]
    original = copy.deepcopy(messages)
    view = context.model_context(messages)
    results = [json.loads(m["content"]) for m in view if m["role"] == "tool"]
    assert results[1]["result"]["datasets"][0]["id"] == 3
    assert results[1]["result"]["overlap"]["omitted_unchanged_records"] == 1
    assert results[2]["result"]["datasets"][0]["table_name"] == "Renamed dataset"
    assert results[0]["available_paths"] == ["datasets", "page"]
    assert len(context.serialized(view)) < 6000
    assert messages == original
    assert_pairs(view)


def test_large_latest_parallel_batch_shrinks_without_breaking_pairs():
    messages = [{"role": "user", "content": "Inspect these resources"}]
    calls = [test_engine.call("inspect", f"parallel-{n}") for n in range(8)]
    messages.append({"role": "assistant", "tool_calls": calls})
    for n in range(8):
        messages.append(
            {
                "role": "tool",
                "tool_call_id": f"parallel-{n}",
                "content": json.dumps({"rows": ["x" * 10000] * 30}),
            }
        )
    view = context.model_context(messages, max_chars=6500)
    assert len(context.serialized(view)) <= 6500
    assert messages[0] in view
    assert len([m for m in view if m["role"] == "tool"]) == 8
    assert_pairs(view)


def test_evidence_paths_and_root_reads_are_bounded_and_retrievable():
    evidence = __import__(f"{test_engine.PACKAGE}.evidence", fromlist=["read_page"])
    raw = {
        "structuredContent": {
            "datasets": [{"id": n, "description": "x" * 10000} for n in range(100)]
        },
        "raw": "duplicate" * 10000,
    }
    root = evidence.read_page(raw, {})
    assert root["truncated"]
    assert len(json.dumps(root)) < 6000
    invalid = evidence.read_page(raw, {"path": ["result", "datasets"]})
    assert invalid["isError"]
    assert invalid["available_paths"] == ["datasets"]
    page = evidence.read_page(raw, {"path": ["datasets"], "limit": 100})
    assert page["next_offset"] == 1
    assert len(json.dumps(page)) < 6000
    exact = evidence.read_page(
        raw, {"path": ["datasets", "0", "description"], "limit": 100}
    )
    assert exact["data"] == "x" * 100
    assert exact["next_offset"] == 100
    assert not exact["truncated"]


def test_discovery_filters_and_connections_do_not_share_overlap_index():
    messages = []
    for n, name, region in [
        (1, "a__list_datasets", "HK"),
        (2, "b__list_datasets", "HK"),
        (3, "a__list_datasets", "KR"),
    ]:
        messages += [
            {
                "role": "assistant",
                "tool_calls": [test_engine.call(name, str(n), {"region": region})],
            },
            {
                "role": "tool",
                "tool_call_id": str(n),
                "content": json.dumps(
                    {
                        "structuredContent": {
                            "datasets": [{"id": 1, "table_name": "Visible"}]
                        }
                    }
                ),
            },
        ]
    view = context.model_context(messages)
    assert all('"overlap"' not in m["content"] for m in view if m["role"] == "tool")


def test_discovery_loop_ends_with_answer_from_evidence_without_further_tools():
    checkpoints = []

    class ObservedProvider(test_engine.Provider):
        async def generate(self, messages, tools, **kwargs):
            if len(self.requests) == 4:
                assert tools == []
                assert "without progress" in context.serialized(messages)
            return await super().generate(messages, tools, **kwargs)

    provider = ObservedProvider(
        [
            *[
                test_engine.contracts.Generation(
                    calls=[test_engine.call("list_data", f"call-{n}")]
                )
                for n in range(4)
            ],
            test_engine.contracts.Generation(
                content="Dataset 9 is available; this is a partial listing."
            ),
        ]
    )
    pool = test_engine.Pool([test_engine.tool("list_data")], checkpoints)
    result = test_engine.run(
        {"_provider": provider, "_mcp_pool": pool, "input_text": "List data"},
        checkpoints,
    )
    assert result["status"] == "completed"
    assert result["checkpoint"]["discovery_exhausted"]
    assert len(pool.invocations) == 1
    assert result["checkpoint"]["discovery"]["interventions"] == 3
    assert "Dataset 9" in result["content"]


def test_bad_evidence_paths_offer_recovery_without_external_dispatch():
    checkpoints = []
    provider = test_engine.Provider(
        [
            test_engine.contracts.Generation(
                calls=[test_engine.call("get_data", "original")]
            ),
            test_engine.contracts.Generation(
                calls=[
                    test_engine.call(
                        "read_evidence",
                        "bad",
                        {"call_id": "original", "path": ["result", "rows"]},
                    )
                ]
            ),
            test_engine.contracts.Generation(
                calls=[
                    test_engine.call(
                        "read_evidence",
                        "good",
                        {"call_id": "original", "path": ["rows"]},
                    )
                ]
            ),
            test_engine.contracts.Generation(content="Read the row"),
        ]
    )
    pool = test_engine.Pool([test_engine.tool()], checkpoints)
    result = test_engine.run({"_provider": provider, "_mcp_pool": pool}, checkpoints)
    replies = {
        m.get("tool_call_id"): json.loads(m["content"])
        for m in result["messages"]
        if m["role"] == "tool"
    }
    assert replies["bad"]["available_paths"] == ["success", "rows"]
    assert replies["good"]["data"] == [{"id": 9}]
    assert len(pool.invocations) == 1
    assert result["checkpoint"]["evidence_path_failures"] == 0


def test_discovery_shaping_preserves_offsets_filters_and_explicit_fields():
    target = test_engine.tool("list_datasets", focal=True)
    target.schema = {
        "type": "object",
        "properties": {
            "request": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1},
                    "select_columns": {"type": "array", "items": {"type": "string"}},
                    "search": {"type": "string"},
                },
                "additionalProperties": False,
            }
        },
        "required": ["request"],
        "additionalProperties": False,
    }
    original = {"request": {"page": 3, "page_size": 100, "search": "Census"}}
    result = test_engine.policy.normalized_arguments(target, original)["request"]
    assert result["page"] == 9
    assert result["page_size"] == 25
    assert result["search"] == "Census"
    assert result["select_columns"] == [
        "id",
        "table_name",
        "schema",
        "database_name",
        "description",
    ]
    assert original["request"]["page_size"] == 100
    explicit = test_engine.policy.normalized_arguments(
        target,
        {
            "request": {
                "page": 2,
                "page_size": 30,
                "select_columns": ["id", "columns"],
            }
        },
    )["request"]
    assert explicit["page"] == 3
    assert explicit["page_size"] == 15
    assert explicit["select_columns"] == ["id", "columns"]
    target.connection["is_focal"] = False
    assert test_engine.policy.normalized_arguments(target, original) == original


def test_evidence_size_bound_and_advertised_paths_remain_valid():
    evidence = __import__(f"{test_engine.PACKAGE}.evidence", fromlist=["read_page"])
    value = {"field" + str(n) + "x" * 100: "y" * 10000 for n in range(40)}
    result = evidence.read_page(value, {"limit": 100})
    assert len(json.dumps(result)) <= 6000
    assert result["truncated"]
    assert all(path in value for path in result["available_paths"])
    assert result["next_offset"] == 1


def test_gpu_sized_schema_and_guidance_leave_room_for_recent_parallel_results():
    messages = [{"role": "user", "content": "What dataset can I use?"}]
    calls = [
        test_engine.call(
            "server__list_datasets",
            f"p{n}",
            {"request": {"page": n + 1, "page_size": 15}},
        )
        for n in range(4)
    ]
    messages.append({"role": "assistant", "tool_calls": calls})
    for n in range(4):
        datasets = [
            {
                "id": n * 15 + k,
                "table_name": f"Dataset {n * 15 + k}",
                "description": "metadata " * 1000,
            }
            for k in range(15)
        ]
        messages.append(
            {
                "role": "tool",
                "tool_call_id": f"p{n}",
                "content": json.dumps(
                    {
                        "structuredContent": {"datasets": datasets, "page": n + 1},
                        "raw": "duplicated transport " * 1000,
                    }
                ),
            }
        )
    memory = {}
    schemas = [{"description": "x" * 50000}]
    view = context.model_context(
        messages,
        tools=schemas,
        guidance=[{"text": "x" * 14500}],
        max_tokens=24576,
        checkpoint=memory,
    )
    assert memory["stats"]["estimated_input_tokens"] <= 24576
    assert messages[0] in view
    assert_pairs(view)


def test_verbose_catalogue_schema_does_not_displace_discovery_records():
    raw = {
        "structuredContent": {
            "datasets": [
                {"id": n, "table_name": f"Census dataset {n}"} for n in range(25)
            ],
            "columns_available": [
                {"name": str(n), "description": "x" * 20000} for n in range(30)
            ],
            "total_count": 63,
            "has_next": True,
            "page": 1,
            "page_size": 25,
        }
    }
    view = context.model_context(
        [{"role": "tool", "tool_call_id": "list", "content": json.dumps(raw)}]
    )
    preview = json.loads(view[0]["content"])
    assert len(preview["result"]["datasets"]) == 25
    assert preview["result"]["total_count"] == 63
    assert preview["result"]["has_next"]
    assert "columns_available" in preview["available_paths"]
    assert "columns_available" not in preview["result"]


def test_evidence_cursor_targets_original_result_not_the_returned_page():
    evidence = __import__(f"{test_engine.PACKAGE}.evidence", fromlist=["read_page"])
    raw = {
        "structuredContent": {
            "datasets": [{"id": n, "description": "x" * 1000} for n in range(25)]
        }
    }
    first = evidence.read_page(
        raw, {"call_id": "original", "path": ["datasets"], "limit": 25}
    )
    next_read = first["next_read"]
    assert next_read["call_id"] == "original"
    assert next_read["path"] == ["datasets"]
    second = evidence.read_page(raw, next_read)
    assert second["offset"] == first["next_offset"]
    assert second["data"][0]["id"] == first["next_offset"]
    wrong = evidence.read_page(
        first, {"call_id": "first_page", "path": ["data"], "offset": 20}
    )
    assert wrong["isError"]
    assert wrong["next_read"] == next_read


def test_successful_evidence_rereads_are_bounded_without_hiding_first_read():
    checkpoints = []
    provider = test_engine.Provider(
        [
            test_engine.contracts.Generation(
                calls=[test_engine.call("get_data", "source")]
            ),
            *[
                test_engine.contracts.Generation(
                    calls=[
                        test_engine.call(
                            "read_evidence",
                            f"read-{n}",
                            {
                                "call_id": "source",
                                "path": ["rows"],
                            },
                        )
                    ]
                )
                for n in range(4)
            ],
            test_engine.contracts.Generation(content="The recorded row has ID 9."),
        ]
    )
    pool = test_engine.Pool([test_engine.tool()], checkpoints)
    result = test_engine.run({"_provider": provider, "_mcp_pool": pool}, checkpoints)
    assert result["status"] == "completed"
    assert result["checkpoint"]["discovery_exhausted"]
    assert len(pool.invocations) == 1
    assert "without progress" in context.serialized(provider.requests[-1])


@pytest.mark.parametrize("overflow", [False, True])
@pytest.mark.parametrize("focused_overflow", [False, True])
def test_sustained_context_pressure_reclaims_schema_capacity_for_partial_answer(
    monkeypatch,
    overflow,
    focused_overflow,
):
    original = test_engine.engine.model_context

    attempts = []

    def pressured(messages, **kwargs):
        attempts.append(True)
        view = original(messages, **kwargs)
        if kwargs.get("tools") and (
            (overflow and len(attempts) == 7)
            or (focused_overflow and len(attempts) >= 8)
        ):
            raise test_engine.contracts.AiRuntimeError(
                "context full", code="context_budget"
            )
        if kwargs.get("tools"):
            kwargs["checkpoint"]["stats"].update(
                estimated_input_tokens=kwargs["max_tokens"],
                summarized_groups=1,
            )
        return view

    monkeypatch.setattr(test_engine.engine, "model_context", pressured)
    checkpoints = []
    provider = test_engine.Provider(
        [
            *[
                test_engine.contracts.Generation(
                    calls=[
                        test_engine.call(
                            "read_evidence",
                            f"page-{n}",
                            {
                                "call_id": "message:1",
                                "path": ["content"],
                                "offset": n,
                                "limit": 1,
                            },
                        )
                    ]
                )
                for n in range(6)
            ],
            test_engine.contracts.Generation(
                content="Partial answer from recorded evidence."
            ),
        ]
    )
    pool = test_engine.Pool([], checkpoints)
    result = test_engine.run(
        {
            "_provider": provider,
            "_mcp_pool": pool,
            "input_text": "abcdefghijklmnopqrstuvwxyz",
        },
        checkpoints,
    )
    assert result["status"] == "completed"
    assert result["checkpoint"]["discovery_recovery"] == "focused_tools"
    if focused_overflow:
        assert result["checkpoint"]["finish_reason"] == "context_pressure"
        assert "explicitly identify unfinished work" in context.serialized(
            provider.requests[-1]
        )
    else:
        assert not result["checkpoint"].get("discovery_exhausted")
    assert not pool.invocations


def test_discovery_preview_explains_coverage_and_supplies_source_read_arguments():
    raw = {
        "structuredContent": {
            "datasets": [{"id": n, "table_name": f"Dataset {n}"} for n in range(25)],
            "total_count": 63,
            "page": 1,
            "has_next": True,
        }
    }
    view = context.model_context(
        [{"role": "tool", "tool_call_id": "original", "content": json.dumps(raw)}]
    )
    preview = json.loads(view[0]["content"])
    assert preview["coverage"]["shown_records"] == 25
    assert preview["coverage"]["page_records"] == 25
    assert preview["coverage"]["total_count"] == 63
    args = preview["read_examples"][0]
    assert args["path"] == ["datasets"]
    evidence = __import__(f"{test_engine.PACKAGE}.evidence", fromlist=["read_page"])
    response = evidence.read_page(raw, args)
    assert response["isError"] is False
    assert response["source_evidence_ref"] == "original"
    assert response["total"] == 25

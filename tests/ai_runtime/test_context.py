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

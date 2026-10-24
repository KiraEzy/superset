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
"""Standalone runtime contract tests, independent of Flask/database fixtures."""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

PACKAGE = "standalone_ai_runtime"
module = types.ModuleType(PACKAGE)
module.__path__ = [
    str(
        Path(
            os.environ.get(
                "AI_RUNTIME_SOURCE",
                str(Path(__import__("superset").__file__).parent / "ai_runtime"),
            )
        )
    )
]
sys.modules.setdefault(PACKAGE, module)
engine = importlib.import_module(f"{PACKAGE}.engine")
contracts = importlib.import_module(f"{PACKAGE}.contracts")
policy = importlib.import_module(f"{PACKAGE}.policy")
mcp = importlib.import_module(f"{PACKAGE}.mcp")
providers = importlib.import_module(f"{PACKAGE}.providers")


class Provider:
    def __init__(self, generations: list[Any]) -> None:
        self.generations = iter(generations)
        self.requests: list[Any] = []

    async def generate(self, messages: Any, tools: Any, **kwargs: Any) -> Any:
        self.requests.append(copy.deepcopy(messages))
        return next(self.generations)


class Pool:
    def __init__(
        self, tools: list[Any], checkpoints: list[Any], *, fail: bool = False
    ) -> None:
        self.tools, self.checkpoints, self.fail = tools, checkpoints, fail
        self.invocations: list[Any] = []
        self.active = 0
        self.peak = 0

    async def __aenter__(self) -> Any:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def discover(self, connections: Any, refresh_auth: Any) -> Any:
        return self.tools

    async def call(self, tool: Any, arguments: Any) -> Any:
        assert any(
            record.get("status") == "in_progress"
            for record in self.checkpoints[-1]["calls"].values()
        )
        self.invocations.append((tool.name, arguments))
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        if self.fail:
            raise OSError("private upstream body must not escape")
        return {
            "isError": False,
            "content": [],
            "structuredContent": {"success": True, "rows": [{"id": 9}]},
        }


def tool(name: str = "get_data", effect: str = "read", focal: bool = False) -> Any:
    return contracts.Tool(
        name,
        name,
        {"id": "c", "is_focal": focal, "url": "https://example.org/mcp"},
        {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        effect=effect,
    )


def call(name: str = "get_data", identifier: str = "call-1", args: Any = None) -> Any:
    return {
        "id": identifier,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args or {"id": 9})},
    }


def run(
    state: Any, checkpoints: list[Any], *, inputs: Any = None, cancelled: Any = None
) -> Any:
    return asyncio.run(
        engine.run_turn(
            state,
            emit=lambda *args: None,
            checkpoint=lambda cp: checkpoints.append(copy.deepcopy(cp)),
            cancelled=cancelled or (lambda: False),
            consume_inputs=lambda: inputs or [],
            refresh_auth=lambda: "explicit-focal-token",
        )
    )


def test_single_final_generation_and_durable_tool_results() -> None:
    checkpoints: list[Any] = []
    provider = Provider(
        [
            contracts.Generation(calls=[call()]),
            contracts.Generation(content="Sourced answer"),
        ]
    )
    pool = Pool([tool()], checkpoints)
    result = run(
        {"_provider": provider, "_mcp_pool": pool, "input_text": "Inspect data"},
        checkpoints,
    )
    assert result["status"] == "completed"
    assert len(provider.requests) == 2
    assert provider.requests[-1][-1]["role"] == "tool"
    assert result["checkpoint"]["calls"]["call-1"]["status"] == "completed"
    assert result["content"] == "Sourced answer"


def test_approval_binds_exact_normalized_arguments_and_resume() -> None:
    checkpoints: list[Any] = []
    provider = Provider(
        [
            contracts.Generation(calls=[call("save")]),
            contracts.Generation(content="Saved"),
        ]
    )
    pool = Pool([tool("save", "write")], checkpoints)
    state = {"_provider": provider, "_mcp_pool": pool}
    first = run(state, checkpoints)
    assert first["status"] == "waiting_approval"
    assert not pool.invocations
    second = run(
        {
            **state,
            "checkpoint": first["checkpoint"],
            "approved_scopes": [first["pending_request"]["fingerprint"]],
        },
        checkpoints,
    )
    assert second["status"] == "completed"
    assert len(pool.invocations) == 1
    assert not policy.authorized(
        pool.tools[0], {"id": 10}, [first["pending_request"]["fingerprint"]]
    )


def test_uncertain_write_is_never_replayed() -> None:
    checkpoints: list[Any] = []
    target = tool("save", "write")
    provider = Provider([contracts.Generation(calls=[call("save")])])
    pool = Pool([target], checkpoints, fail=True)
    state = {
        "_provider": provider,
        "_mcp_pool": pool,
        "approved_scopes": [policy.fingerprint(target, {"id": 9})],
    }
    first = run(state, checkpoints)
    assert first["status"] == "needs_review"
    assert len(pool.invocations) == 1
    resumed = run({**state, "checkpoint": first["checkpoint"]}, checkpoints)
    assert resumed["status"] == "needs_review"
    assert len(pool.invocations) == 1


def test_reads_retry_at_most_twice_and_concurrency_four() -> None:
    checkpoints: list[Any] = []
    provider = Provider(
        [
            contracts.Generation(calls=[call(identifier=f"c-{i}") for i in range(7)]),
            contracts.Generation(content="Done"),
        ]
    )
    pool = Pool([tool()], checkpoints)
    assert (
        run({"_provider": provider, "_mcp_pool": pool}, checkpoints)["status"]
        == "completed"
    )
    assert pool.peak == 4
    failing = Pool([tool()], checkpoints, fail=True)
    provider = Provider(
        [contracts.Generation(calls=[call()]), contracts.Generation(content="Failed")]
    )
    run({"_provider": provider, "_mcp_pool": failing}, checkpoints)
    assert len(failing.invocations) == 3  # initial attempt plus two retries


def test_clarification_resume_and_cancellation() -> None:
    checkpoints: list[Any] = []
    provider = Provider(
        [
            contracts.Generation(
                calls=[call("ask_user", args={"question": "Which period?"})]
            ),
            contracts.Generation(content="Proceed"),
        ]
    )
    pool = Pool([], checkpoints)
    state = {"_provider": provider, "_mcp_pool": pool}
    first = run(state, checkpoints)
    assert first["status"] == "waiting_input"
    resumed = run(
        {
            **state,
            "checkpoint": first["checkpoint"],
            "pending_response": {"input": "October"},
        },
        checkpoints,
    )
    assert resumed["status"] == "completed"
    assert json.loads(provider.requests[-1][-1]["content"])["answer"] == "October"
    assert run(state, checkpoints, cancelled=lambda: True)["status"] == "cancelled"


def test_full_schema_validation_and_no_annotation_trust() -> None:
    target = tool(effect="unknown")
    with pytest.raises(contracts.AiRuntimeError):
        policy.normalized_arguments(target, {"id": "9"})
    assert not policy.authorized(
        target, {"id": 9}, ["get_data", {"tool": "get_data", "approved": True}]
    )


def test_text_backed_superset_error_and_artifact_data() -> None:
    value = mcp.normalize_result(
        {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": '{"success":true,"form_data":{"dataset_id":4}}',
                }
            ],
        }
    )
    assert value["isError"] is True
    assert value["structuredContent"]["form_data"]["dataset_id"] == 4
    assert mcp.normalize_result(
        {"content": [{"type": "text", "text": '{"success":false}'}]}
    )["isError"]


def test_responses_conversion_preserves_call_identity() -> None:
    items = providers.response_input(
        [
            {"role": "assistant", "content": None, "tool_calls": [call()]},
            {"role": "tool", "tool_call_id": "call-1", "content": "result"},
        ]
    )
    assert items[0]["call_id"] == items[1]["call_id"] == "call-1"
    assert items[0]["type"] == "function_call"


def test_preview_default_prevents_accidental_persistence() -> None:
    target = tool("generate_chart", "write", True)
    target.schema = {
        "type": "object",
        "properties": {
            "request": {
                "type": "object",
                "properties": {"save_chart": {"type": "boolean"}},
                "additionalProperties": False,
            }
        },
        "required": ["request"],
    }
    args = policy.normalized_arguments(target, {})
    assert args == {"request": {"save_chart": False}}
    assert policy.effect_for(target, args) == "read"
    assert policy.effect_for(target, {"request": {"save_chart": True}}) == "write"


def test_invalid_arguments_are_reported_to_model_without_tool_dispatch():
    checkpoints = []
    provider = Provider(
        [
            contracts.Generation(calls=[call(args={"id": "wrong-type"})]),
            contracts.Generation(calls=[call(identifier="corrected", args={"id": 9})]),
            contracts.Generation(content="Corrected"),
        ]
    )
    pool = Pool([tool()], checkpoints)
    result = run({"_provider": provider, "_mcp_pool": pool}, checkpoints)
    assert result["status"] == "completed"
    assert len(pool.invocations) == 1
    error = json.loads(provider.requests[1][-1]["content"])
    assert error["isError"] and error["validation"]["path"] == ["id"]


def test_remote_schema_references_are_rejected_before_resolution():
    with pytest.raises(contracts.AiRuntimeError, match="unsupported"):
        policy.schema_validator({"$ref": "https://private.invalid/schema"})


def test_large_structured_evidence_does_not_duplicate_raw_transport_content():
    context = importlib.import_module(f"{PACKAGE}.context")
    result = {
        "structuredContent": {"rows": [{"id": i} for i in range(1000)]},
        "raw": {"content": [{"text": "duplicate" * 10000}]},
        "content": [{"text": "duplicate" * 10000}],
        "isError": False,
    }
    messages = [
        {"role": "tool", "tool_call_id": "evidence-1", "content": json.dumps(result)}
    ]
    view = context.model_context(messages, max_chars=6000)
    parsed = json.loads(view[0]["content"])
    assert parsed["evidence_ref"] == "evidence-1"
    assert "raw" not in parsed["result"]
    assert len(messages[0]["content"]) > 100000


def test_steering_cancels_undispatched_calls_at_safe_boundary():
    checkpoints = []
    provider = Provider(
        [
            contracts.Generation(calls=[call("save")]),
            contracts.Generation(content="No save performed"),
        ]
    )
    target = tool("save", "write")
    pool = Pool([target], checkpoints)
    delivered = False

    def consume():
        nonlocal delivered
        if not delivered and provider.requests:
            delivered = True
            return [{"input": "Do not save; explain the preview only"}]
        return []

    result = asyncio.run(
        engine.run_turn(
            {"_provider": provider, "_mcp_pool": pool},
            emit=lambda *args: None,
            checkpoint=lambda cp: checkpoints.append(copy.deepcopy(cp)),
            cancelled=lambda: False,
            consume_inputs=consume,
            refresh_auth=lambda: None,
        )
    )
    assert result["status"] == "completed"
    assert not pool.invocations
    assert result["checkpoint"]["calls"]["call-1"]["status"] == "cancelled"


def test_native_preview_includes_datasource_without_changing_raw_result():
    artifacts = importlib.import_module(f"{PACKAGE}.artifacts")
    value = {
        "isError": False,
        "structuredContent": {
            "chart": {"id": 55, "slice_name": "Saved", "viz_type": "table"},
            "form_data": {"viz_type": "table", "all_columns": ["name"]},
        },
    }
    result = artifacts.extract_artifacts("generate_chart", "call-1", value)
    assert len([item for item in result if item["type"] == "chart"]) == 1
    assert result[0]["data"]["slice_id"] == 55
    assert "datasource" not in value["structuredContent"]["form_data"]


def test_stop_after_read_prevents_following_approval_or_write():
    checkpoints = []
    provider = Provider([contracts.Generation(calls=[call(), call("save", "write-2")])])
    pool = Pool([tool(), tool("save", "write")], checkpoints)
    result = run(
        {"_provider": provider, "_mcp_pool": pool},
        checkpoints,
        cancelled=lambda: bool(pool.invocations),
    )
    assert result["status"] == "cancelled"
    assert len(pool.invocations) == 1


def test_guidance_accepted_during_final_generation_is_not_lost():
    checkpoints = []
    provider = Provider(
        [
            contracts.Generation(content="Initial"),
            contracts.Generation(content="Revised"),
        ]
    )
    delivered = False

    def consume():
        nonlocal delivered
        if provider.requests and not delivered:
            delivered = True
            return [{"input": "Also explain the filters"}]
        return []

    result = asyncio.run(
        engine.run_turn(
            {"_provider": provider, "_mcp_pool": Pool([], checkpoints)},
            emit=lambda *args: None,
            checkpoint=lambda cp: checkpoints.append(copy.deepcopy(cp)),
            cancelled=lambda: False,
            consume_inputs=consume,
            refresh_auth=lambda: None,
        )
    )
    assert result["status"] == "completed"
    assert len(provider.requests) == 2
    assert provider.requests[-1][-1]["content"] == "Also explain the filters"


def test_reported_write_error_requires_review_without_model_retry():
    checkpoints = []
    target = tool("save", "write")
    provider = Provider([contracts.Generation(calls=[call("save")])])
    pool = Pool([target], checkpoints)

    async def rejected(tool, arguments):
        pool.invocations.append((tool.name, arguments))
        return {"isError": True, "structuredContent": {"success": False}}

    pool.call = rejected
    result = run(
        {
            "_provider": provider,
            "_mcp_pool": pool,
            "approved_scopes": [policy.fingerprint(target, {"id": 9})],
        },
        checkpoints,
    )
    assert result["status"] == "needs_review"
    assert len(pool.invocations) == 1


def test_admin_revocation_is_checked_before_dispatch_and_is_not_uncertain_write():
    checkpoints = []
    target = tool("save", "write")
    pool = Pool([target], checkpoints)

    def deny(name):
        raise contracts.AiRuntimeError(
            "Denied by administrator", code="tool_access_denied"
        )

    with pytest.raises(contracts.AiRuntimeError) as caught:
        run(
            {
                "_provider": Provider([contracts.Generation(calls=[call("save")])]),
                "_mcp_pool": pool,
                "_authorize_tool": deny,
                "approved_scopes": [policy.fingerprint(target, {"id": 9})],
            },
            checkpoints,
        )
    assert caught.value.code == "tool_access_denied"
    assert not any(
        record.get("status") == "in_progress"
        for record in checkpoints[-1]["calls"].values()
    )
    assert not pool.invocations


def test_usage_counts_tokens_but_does_not_add_provider_speed_gauges():
    checkpoints = []
    provider = Provider(
        [
            contracts.Generation(
                calls=[call()],
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 5,
                    "tokens_per_second": 10,
                },
            ),
            contracts.Generation(
                content="Answer",
                usage={
                    "prompt_tokens": 120,
                    "completion_tokens": 10,
                    "tokens_per_second": 12,
                },
            ),
        ]
    )
    result = run(
        {"_provider": provider, "_mcp_pool": Pool([tool()], checkpoints)}, checkpoints
    )
    assert result["usage"]["prompt_tokens"] == 220
    assert result["usage"]["completion_tokens"] == 15
    assert result["usage"]["tokens_per_second"] == 12

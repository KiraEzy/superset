# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
"""Protocol-group trimming, overflow recovery and private wire-image contracts."""

import asyncio
import copy
import importlib
from typing import Any

import httpx
import pytest
import test_native_sdk as n
from openai import BadRequestError
from test_native_sdk import database as shared_database

from superset.utils import json

context = importlib.import_module(f"{n.t.PACKAGE}.native_context")
model_module = importlib.import_module(f"{n.t.PACKAGE}.native_model")


database = shared_database


def test_trim_complete_active_batches_preserves_pending_calls() -> None:
    items: list[Any] = [{"role": "user", "content": "Continue the chart task"}]
    for index in range(8):
        items += [
            {"type": "reasoning", "summary": [{"text": "private reasoning" * 1000}]},
            {
                "type": "function_call",
                "call_id": str(index),
                "name": "read",
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "call_id": str(index),
                "output": "result" * 1000,
            },
        ]
    items += [
        {
            "type": "function_call",
            "call_id": "pending",
            "name": "read",
            "arguments": "{}",
        }
    ]
    original = copy.deepcopy(items)
    view, note = context.fit_input(items, "required instructions", [], 2000)
    calls = {i["call_id"] for i in view if i.get("type") == "function_call"}
    outputs = {i["call_id"] for i in view if i.get("type") == "function_call_output"}
    assert calls - outputs == {"pending"}
    assert outputs <= calls
    assert "0" in note
    assert "read_evidence" in note
    assert "private reasoning" not in note
    assert items == original


def state(database: Any, handler: Any, cp: Any = None) -> dict[str, Any]:
    session = n.session(database, turn="accepted")
    session.offset = (cp or {}).get("session_offset", 0)
    return {
        "execution_version": 3,
        "execution_sdk_version": "0.10.5",
        "config": {
            "llmApiBaseUrl": "https://provider.test/v1",
            "llmModel": "deepseek-test",
        },
        "input_text": "Question",
        "checkpoint": cp or {},
        "_native_session": session,
        "_native_transport": httpx.MockTransport(handler),
        "_mcp_pool": n.t.Pool([], []),
        "budgets": {"context_window_tokens": 100000},
        "user_id": 1,
        "post_id": 2,
    }


async def run(value: Any, *, cancelled: Any = lambda: False) -> Any:
    return await n.native.run_native(
        value,
        emit=lambda *args: None,
        checkpoint=lambda cp: None,
        cancelled=cancelled,
        refresh_auth=lambda: "token",
    )


def test_oversize_pauses_then_focused_input_reuses_session(database: Any) -> None:
    requests = []

    async def handler(request: Any) -> Any:
        requests.append(json.loads(request.content))
        return n.streamed_response()

    async def exercise() -> None:
        initial = state(database, handler)
        initial["input_text"] = "x" * 60000
        initial["budgets"] = {"context_window_tokens": 22000}
        paused = await run(initial)
        assert paused["status"] == "waiting_input"
        assert paused["pending_request"]["reason"] == "context"
        assert requests == []
        focused = state(database, handler, paused["checkpoint"])
        focused["budgets"] = initial["budgets"]
        focused["pending_response"] = {"input": "A brief overview"}
        result = await run(focused)
        assert result["status"] == "completed"
        saved = await focused["_native_session"].get_items()
        assert saved[0]["content"] == "x" * 60000
        assert sum(i.get("role") == "user" for i in saved) == 2

    asyncio.run(exercise())
    assert sum(bool(request.get("stream")) for request in requests) == 1
    assert "x" * 60000 not in json.dumps(requests)


def test_image_bytes_exist_only_on_authorized_wire(database: Any) -> None:
    requests = []

    async def handler(request: Any) -> Any:
        requests.append(json.loads(request.content))
        return n.streamed_response()

    def hydrate(messages: Any, config: Any) -> Any:
        assert config["image_user_id"] == 1
        assert config["image_post_id"] == 2
        assert messages[0]["content"][0]["image_id"] == "owned-image"
        return [
            {
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,cGl4ZWw="},
                    }
                ]
            }
        ]

    async def exercise() -> None:
        initial = state(database, handler)
        initial["config"]["vision"] = True
        initial["attachment_ids"] = ["owned-image"]
        initial["_native_hydrate"] = hydrate
        result = await run(initial)
        assert result["status"] == "completed"
        saved = await initial["_native_session"].get_items()
        assert "focal-image:owned-image" in json.dumps(saved)
        assert "cGl4ZWw=" not in json.dumps(saved)

    asyncio.run(exercise())
    assert "cGl4ZWw=" in json.dumps(requests)


def test_cancellation_interrupts_stalled_model(database: Any) -> None:
    stopped = False
    released = False

    async def handler(request: Any) -> Any:
        nonlocal released
        try:
            await asyncio.Event().wait()
        finally:
            released = True

    async def exercise() -> None:
        nonlocal stopped

        async def cancel() -> None:
            nonlocal stopped
            await asyncio.sleep(0.05)
            stopped = True

        monitor = asyncio.create_task(cancel())
        with pytest.raises(n.t.contracts.TurnCancelledError):
            await asyncio.wait_for(
                run(state(database, handler), cancelled=lambda: stopped), 2
            )
        await monitor

    asyncio.run(exercise())
    assert released


@pytest.mark.parametrize("context_error", [True, False])
def test_only_context_errors_retry_model(context_error: bool) -> None:
    from agents import Agent, RunConfig, Runner

    requests = []

    async def handler(request: Any) -> Any:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "context_length_exceeded"
                        if context_error
                        else "invalid_parameter",
                        "message": "Request rejected",
                    }
                },
            )
        return n.streamed_response()

    async def exercise() -> None:
        model, client = model_module.create_model(
            {"llmApiBaseUrl": "https://provider.test/v1", "llmModel": "test"},
            {},
            transport=httpx.MockTransport(handler),
        )

        async def consume() -> None:
            result = Runner.run_streamed(
                Agent(name="test", model=model),
                "question",
                run_config=RunConfig(tracing_disabled=True),
            )
            async for _ in result.stream_events():
                pass

        try:
            if context_error:
                await consume()
            else:
                with pytest.raises(BadRequestError):
                    await consume()
        finally:
            await client.close()

    asyncio.run(exercise())
    assert len(requests) == (2 if context_error else 1)


def test_application_metadata_checkpoint_gets_native_defaults(database: Any) -> None:
    async def handler(request: Any) -> Any:
        return n.streamed_response()

    async def exercise() -> None:
        result = await run(state(database, handler, {"artifact_refs": []}))
        assert result["status"] == "completed"
        assert result["checkpoint"]["content"]
        assert result["checkpoint"]["calls"] == {}

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "provider,enabled,expected",
    [
        ("custom", True, True),
        ("custom", False, False),
        ("deepseek", True, True),
        ("deepseek", False, False),
        ("openai", True, False),
    ],
)
def test_reasoning_display_requires_existing_provider_opt_in(
    database: Any, provider: str, enabled: bool, expected: bool
) -> None:
    async def handler(request: Any) -> Any:
        return n.streamed_response()

    async def exercise() -> None:
        value = state(database, handler)
        value["config"].update(llmProvider=provider, showModelReasoning=enabled)
        events = []
        await n.native.run_native(
            value,
            emit=lambda kind, payload: events.append((kind, payload)),
            checkpoint=lambda cp: None,
            cancelled=lambda: False,
            refresh_auth=lambda: "token",
        )
        shown = [payload for kind, payload in events if kind == "model_reasoning"]
        assert bool(shown) == expected
        if shown:
            assert shown[-1]["completed"] is True

    asyncio.run(exercise())


@pytest.mark.parametrize("context_window", [22000, 1000000])
def test_full_catalogue_respects_context_budget(
    database: Any,
    context_window: int,
) -> None:
    requests = []

    async def handler(request: Any) -> Any:
        value = json.loads(request.content)
        requests.append(value)
        assert {tool["function"]["name"] for tool in value["tools"]} == {
            *(f"tool_{i}" for i in range(100)),
            "read_evidence",
            "read_artifact",
            "present_deliverable",
            "ask_user",
            "find_bi_tools",
        }
        return n.streamed_response()

    async def exercise() -> None:
        value = state(database, handler)
        value["budgets"]["context_window_tokens"] = context_window
        tools = [
            n.t.contracts.Tool(
                f"tool_{i}",
                f"tool_{i}",
                {"id": "private"},
                {
                    "type": "object",
                    "properties": {
                        "search": {
                            "type": "string",
                            "description": "schema text " * 100,
                        }
                    },
                },
                "Find evidence",
                effect="read",
            )
            for i in range(100)
        ]
        value["_mcp_pool"] = n.t.Pool(tools, [])
        result = await run(value)
        assert result["status"] == (
            "completed" if context_window == 1000000 else "waiting_input"
        )
        if context_window == 22000:
            assert result["pending_request"]["reason"] == "context"

    asyncio.run(exercise())
    assert len(requests) == (1 if context_window == 1000000 else 0)


def test_invalid_preview_returns_correctable_tool_error_and_no_artifact(
    database: Any, monkeypatch: Any
) -> None:
    requests = []
    checkpoints: list[Any] = []

    async def handler(request: Any) -> Any:
        requests.append(json.loads(request.content))
        return n.streamed_response(call=len(requests) == 1)

    def reject(payload: Any) -> Any:
        raise n.t.contracts.AiRuntimeError(
            "Invalid chart references: missing", code="invalid_preview"
        )

    async def exercise() -> None:
        value = state(database, handler)
        tool = n.t.contracts.Tool(
            "datasets",
            "list_datasets",
            {"id": "focalbi", "is_focal": True},
            {"type": "object", "properties": {}},
            "Read data",
        )
        value["_mcp_pool"] = n.t.Pool([tool], checkpoints)
        value["_validate_preview"] = reject
        monkeypatch.setattr(
            n.native,
            "extract_artifacts",
            lambda *args: [
                {"type": "chart", "data": {"form_data": {"datasource": "1__table"}}}
            ],
        )
        result = await n.native.run_native(
            value,
            emit=lambda *args: None,
            checkpoint=checkpoints.append,
            cancelled=lambda: False,
            refresh_auth=lambda: "token",
        )
        assert result["status"] == "completed"
        assert result["artifacts"] == []
        assert "Invalid chart references" in json.dumps(requests[-1])

    asyncio.run(exercise())


@pytest.mark.parametrize("verified,accessible", [(False, True), (True, False)])
def test_private_images_fail_closed_before_transport(
    database: Any, verified: bool, accessible: bool
) -> None:
    requests = []

    async def handler(request: Any) -> Any:
        requests.append(request)
        return n.streamed_response()

    def hydrate(*args: Any) -> Any:
        raise ValueError("Conversation image is unavailable")

    async def exercise() -> None:
        value = state(database, handler)
        value["attachment_ids"] = ["private-image"]
        value["config"]["vision"] = verified
        if not accessible:
            value["_native_hydrate"] = hydrate
        with pytest.raises(n.t.contracts.AiRuntimeError, match="image"):
            await run(value)
        assert requests == []

    asyncio.run(exercise())


def test_native_model_never_silently_switches_a_responses_connection():
    with pytest.raises(n.t.contracts.AiRuntimeError, match="Chat Completions"):
        model_module.create_model({"adapter": "responses"}, {})

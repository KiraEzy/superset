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
"""Actual Runner/session/wire tests, independent of live model availability."""

import asyncio
import importlib
from typing import Any
from uuid import uuid4

import httpx
import pytest
import test_engine as t
from sqlalchemy import create_engine, Text
from sqlalchemy.orm import sessionmaker

from superset.utils import json

pytest.importorskip("agents")
native = importlib.import_module(f"{t.PACKAGE}.native_engine")
storage = importlib.import_module(f"{t.PACKAGE}.native_session")
models = storage.session_models(Text())


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    storage.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def session(database, *, owner=1, turn=None):
    return storage.FocalSession(
        "thread",
        database=database,
        models=models,
        owner_id=owner,
        post_id=2,
        binding="model",
        turn_id=turn or str(uuid4()),
        guard=lambda: None,
    )


def streamed_response(
    *, call=False, call_id="call-1", name="datasets", arguments=None, usage=None
):
    deltas = [{"role": "assistant", "reasoning_content": "provider-private-test"}]
    if call:
        deltas += [
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": "{"},
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {"arguments": json.dumps(arguments or {})[1:]},
                    }
                ]
            },
        ]
    else:
        deltas += [{"content": "Datasets available."}]
    chunks = [
        {
            "id": "completion",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "deepseek-test",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        for delta in deltas
    ]
    chunks.append(
        {
            "id": "completion",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "deepseek-test",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "tool_calls" if call else "stop",
                }
            ],
        }
    )
    if usage is not None:
        chunks[-1]["usage"] = usage
    payload = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(payload + "data: [DONE]\n\n").encode(),
    )


def test_runner_uses_session_input_and_preserves_reasoning(database):
    requests, events, cps = [], [], []
    tool = t.contracts.Tool(
        "datasets",
        "list_datasets",
        {"id": "focalbi", "is_focal": True},
        {"type": "object", "properties": {}},
        "List datasets",
    )
    pool = t.Pool([tool], cps)

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return streamed_response(
            call=len(requests) <= 2, call_id=f"call-{len(requests)}"
        )

    async def exercise():
        for index, prompt in enumerate(
            ["List available datasets", "Explain those datasets"]
        ):
            result = await native.run_native(
                {
                    "execution_version": 3,
                    "execution_sdk_version": "0.10.5",
                    "config": {
                        "llmApiBaseUrl": "https://provider.test/v1",
                        "llmModel": "deepseek-test",
                        "llmProvider": "deepseek",
                    },
                    "input_text": prompt,
                    "messages": [{"role": "user", "content": "DO NOT SEND LEGACY"}],
                    "_native_session": session(database),
                    "_native_transport": httpx.MockTransport(handler),
                    "_mcp_pool": pool,
                    "_native_thinking": index == 0,
                    "budgets": {"context_window_tokens": 100000},
                },
                emit=lambda k, p: events.append((k, p)),
                checkpoint=cps.append,
                cancelled=lambda: False,
                refresh_auth=lambda: "token",
            )
            assert result["status"] == "completed"
            assert result["checkpoint"]["active_seconds"] > 0
        saved = await session(database).get_items()
        assert [x["content"] for x in saved if x.get("role") == "user"] == [
            "List available datasets",
            "Explain those datasets",
        ]

    asyncio.run(exercise())
    assert len(requests) == 4
    assert "DO NOT SEND LEGACY" not in json.dumps(requests)
    assistants = [m for m in requests[-1]["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 3
    assert all(m["reasoning_content"] == "provider-private-test" for m in assistants)
    assert requests[0]["thinking"]["type"] == "enabled"
    assert requests[-1]["thinking"]["type"] == "disabled"
    assert any(
        m["role"] == "tool" and "result" in m["content"]
        for m in requests[1]["messages"]
    )
    assert len(pool.invocations) == 2
    assert any(k == "message_delta" for k, _ in events)
    assert "provider-private-test" not in json.dumps(events)


def test_session_scope_and_idempotent_append(database):
    async def exercise():
        first = session(database, turn="accepted")
        await first.add_items([{"role": "user", "content": "same"}])
        retry = session(database, turn="accepted")
        await retry.add_items([{"role": "user", "content": "same"}])
        next_turn = session(database)
        await next_turn.add_items([{"role": "user", "content": "same"}])
        assert len(await next_turn.get_items()) == 2
        assert len(await next_turn.get_items(limit=1)) == 1
        assert await next_turn.get_items(limit=0) == []
        with pytest.raises(t.contracts.AiRuntimeError, match="scope"):
            await session(database, owner=99).get_items()

    asyncio.run(exercise())


def test_wire_budget_rejects_before_transport(database):
    from agents import Agent, RunConfig, Runner

    model_module = importlib.import_module(f"{t.PACKAGE}.native_model")
    calls = []

    async def handler(request):
        calls.append(request)
        return streamed_response()

    async def exercise():
        model, client = model_module.create_model(
            {"llmApiBaseUrl": "https://provider.test/v1", "llmModel": "deepseek-test"},
            {"context_window_tokens": 8200},
            transport=httpx.MockTransport(handler),
        )

        async def consume():
            run = Runner.run_streamed(
                Agent(name="test", model=model),
                "long input" * 1000,
                run_config=RunConfig(tracing_disabled=True),
            )
            async for _ in run.stream_events():
                pass

        try:
            with pytest.raises(t.contracts.AiRuntimeError, match="cannot fit"):
                await consume()
        finally:
            await client.close()

    asyncio.run(exercise())
    assert calls == []


def test_input_filter_changes_wire_without_erasing_session(database):
    from agents import Agent, RunConfig, Runner

    model_module = importlib.import_module(f"{t.PACKAGE}.native_model")
    requests = []

    async def handler(request):
        requests.append(json.loads(request.content))
        return streamed_response()

    async def exercise():
        saved = session(database, turn="seed")
        await saved.add_items(
            [
                {"role": "user", "content": "OLDER_CONTEXT" * 1000},
                {"role": "assistant", "content": "Previous answer"},
            ]
        )
        budgets = {"context_window_tokens": 8500}
        model, client = model_module.create_model(
            {"llmApiBaseUrl": "https://provider.test/v1", "llmModel": "deepseek-test"},
            budgets,
            transport=httpx.MockTransport(handler),
        )
        try:
            run = Runner.run_streamed(
                Agent(name="test", model=model),
                "New question",
                session=session(database),
                run_config=RunConfig(
                    tracing_disabled=True,
                    call_model_input_filter=model_module.context_filter(budgets, []),
                ),
            )
            async for _ in run.stream_events():
                pass
            all_items = await saved.get_items()
            assert all_items[0]["content"] == "OLDER_CONTEXT" * 1000
            assert sum(x.get("role") == "user" for x in all_items) == 2
        finally:
            await client.close()

    asyncio.run(exercise())
    assert "OLDER_CONTEXT" * 1000 not in json.dumps(requests)
    assert "New question" in json.dumps(requests)


@pytest.mark.parametrize("old_selection", [None, ["tool_17"]])
def test_all_authorized_tools_remain_offered_after_search(
    database: Any, old_selection: list[str] | None
) -> None:
    requests: list[Any] = []
    checkpoints: list[Any] = []
    tools = [
        t.contracts.Tool(
            f"tool_{index}",
            "get_chart_info",
            {"id": "focalbi", "is_focal": True},
            {"type": "object", "properties": {}},
            f"Read chart metadata {index}",
        )
        for index in range(18)
    ]
    tools.append(
        t.contracts.Tool(
            "denied_tool",
            "blocked_resource",
            {"id": "focalbi", "is_focal": True},
            {"type": "object", "properties": {}},
            "Unauthorized resource",
        )
    )
    pool = t.Pool(tools, checkpoints)
    expected = {tool.name for tool in tools[:-1]} | {
        "read_evidence",
        "read_artifact",
        "present_deliverable",
        "ask_user",
        "find_bi_tools",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert {item["function"]["name"] for item in body["tools"]} == expected
        if len(requests) == 1:
            return streamed_response(
                call=True, name="find_bi_tools", arguments={"query": "chart"}
            )
        if len(requests) == 2:
            search = json.loads(
                next(
                    item["content"]
                    for item in reversed(body["messages"])
                    if item["role"] == "tool"
                )
            )
            assert {item["name"] for item in search["tools"]} == {
                tool.name for tool in tools[:-1]
            }
            return streamed_response(call=True, name="tool_0", call_id="call-2")
        return streamed_response()

    async def exercise() -> None:
        result = await native.run_native(
            {
                "execution_version": 3,
                "execution_sdk_version": "0.10.5",
                "config": {
                    "llmApiBaseUrl": "https://provider.test/v1",
                    "llmModel": "deepseek-test",
                    "llmProvider": "deepseek",
                },
                "input_text": "Inspect charts",
                "checkpoint": {
                    "selected_tools": old_selection,
                    "offered_tools": ["tool_17"],
                }
                if old_selection is not None
                else {},
                "_native_session": session(database),
                "_native_transport": httpx.MockTransport(handler),
                "_mcp_pool": pool,
                "_tool_filter": lambda name: name != "blocked_resource",
                "budgets": {"context_window_tokens": 100000},
            },
            emit=lambda k, p: None,
            checkpoint=checkpoints.append,
            cancelled=lambda: False,
            refresh_auth=lambda: "token",
        )
        assert result["status"] == "completed"
        assert set(result["checkpoint"]["offered_tools"]) == expected
        assert "selected_tools" not in result["checkpoint"]

    asyncio.run(exercise())
    assert len(requests) == 3
    assert pool.invocations == [("tool_0", {})]


def test_context_usage_reports_latest_request_not_cumulative_tokens(
    database: Any,
) -> None:
    events: list[Any] = []
    checkpoints: list[Any] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        return streamed_response(
            usage={"prompt_tokens": 321, "completion_tokens": 45, "total_tokens": 366}
        )

    async def exercise() -> None:
        result = await native.run_native(
            {
                "execution_version": 3,
                "execution_sdk_version": "0.10.5",
                "config": {
                    "llmApiBaseUrl": "https://provider.test/v1",
                    "llmModel": "deepseek-test",
                    "llmProvider": "deepseek",
                },
                "input_text": "Answer briefly",
                "_native_session": session(database),
                "_native_transport": httpx.MockTransport(handler),
                "_mcp_pool": t.Pool([], checkpoints),
                "budgets": {"context_window_tokens": 100000, "response_tokens": 16384},
            },
            emit=lambda k, p: events.append((k, p)),
            checkpoint=checkpoints.append,
            cancelled=lambda: False,
            refresh_auth=lambda: "token",
        )
        usage = result["checkpoint"]["context_usage"]
        assert usage["input_tokens"] == 321
        assert usage["output_tokens"] == 45
        assert usage["context_window_tokens"] == 100000
        assert usage["output_limit_tokens"] == 16384
        assert usage["estimated"] is False
        estimates = [p["usage"] for k, p in events if k == "usage"]
        assert estimates[0]["estimated"] is True
        assert estimates[0]["input_tokens"] > 0
        assert estimates[-1] == usage

    asyncio.run(exercise())


def test_present_deliverable_is_an_sdk_helper_without_mcp_writes(database: Any) -> None:
    import test_native_context as context_tests

    calls: list[Any] = []
    requests: list[Any] = []

    async def handler(request: Any) -> Any:
        requests.append(json.loads(request.content))
        return streamed_response(
            call=len(requests) == 1,
            name="present_deliverable",
            arguments={"artifact_id": "exact-artifact", "title": "Final table"},
        )

    value = context_tests.state(database, handler)
    value["_present_deliverable"] = lambda args, operation_id: calls.append(args) or {
        "key": "visual:exact-artifact"
    }
    result = asyncio.run(context_tests.run(value))
    assert result["status"] == "completed"
    assert calls == [{"artifact_id": "exact-artifact", "title": "Final table"}]
    assert any(
        tool["function"]["name"] == "present_deliverable"
        for tool in requests[0]["tools"]
    )

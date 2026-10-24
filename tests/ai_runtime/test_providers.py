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
"""Streaming adapter tests using deterministic HTTP doubles."""

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from superset.ai_runtime.contracts import AiRuntimeError
from superset.ai_runtime.providers import HTTPProvider
from superset.utils import json


class Response:
    status_code = 200

    def __init__(self, events):
        self.events = events

    async def aiter_lines(self):
        for event in self.events:
            yield "data: " + json.dumps(event)
            yield ""
        yield "data: [DONE]"
        yield ""


def install(monkeypatch, events, requests):
    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            requests.append(kwargs["json"])
            yield Response(events)

    monkeypatch.setattr(httpx, "AsyncClient", Client)


@pytest.mark.parametrize("adapter", ["chat_completions", "responses"])
@pytest.mark.parametrize("with_tools", [False, True])
def test_tool_free_requests_omit_tools_and_enabled_tools_remain_available(
    monkeypatch, adapter, with_tools
):
    captured = []
    events = (
        [{"type": "response.completed", "response": {"id": "r1", "output": []}}]
        if adapter == "responses"
        else [{"choices": [{"delta": {"content": "Done"}, "finish_reason": "stop"}]}]
    )
    install(monkeypatch, events, captured)
    function = {"name": "list_datasets", "parameters": {"type": "object"}}
    tools = [{"type": "function", "function": function}] if with_tools else []
    asyncio.run(
        HTTPProvider(
            {"llmAdapter": adapter, "llmApiBaseUrl": "https://example.test/v1"}
        ).generate(
            [{"role": "user", "content": "Summarize recorded evidence"}],
            tools,
            emit=lambda *_: None,
            cancelled=lambda: False,
            continuation={},
        )
    )
    assert len(captured) == 1
    if with_tools:
        assert captured[0]["tools"] == (
            [{"type": "function", **function}] if adapter == "responses" else tools
        )
    else:
        assert "tools" not in captured[0]


def test_qwen_compatible_stream_accepts_nullable_optional_delta_fields(monkeypatch):
    captured = []
    install(
        monkeypatch,
        [
            {"choices": [{"delta": {"content": None, "tool_calls": None}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {
                                        "name": "health_check",
                                        "arguments": None,
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"name": None, "arguments": "{}"},
                                }
                            ]
                        }
                    }
                ]
            },
            {"choices": [{"delta": None, "finish_reason": "tool_calls"}]},
            {"choices": None, "usage": {"total_tokens": 12}},
        ],
        captured,
    )
    result = asyncio.run(
        HTTPProvider(
            {"llmApiBaseUrl": "https://example.test/v1", "llmModel": "test"}
        ).generate(
            [{"role": "user", "content": "Check health"}],
            [],
            emit=lambda *args: None,
            cancelled=lambda: False,
            continuation={},
        )
    )
    assert result.calls == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "health_check", "arguments": "{}"},
        }
    ]
    assert result.usage == {"total_tokens": 12}
    assert len(captured) == 1


def test_deepseek_protocol_fields_are_replayed_without_public_reasoning(monkeypatch):
    captured, emitted = [], []
    events = [
        {"choices": [{"delta": {"reasoning_content": "private protocol "}}]},
        {
            "choices": [
                {
                    "delta": {
                        "reasoning_content": "continuation",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "inspect", "arguments": "{}"},
                            }
                        ],
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    install(monkeypatch, events, captured)
    provider = HTTPProvider(
        {"llmApiBaseUrl": "https://example.test/v1", "llmModel": "test"}
    )

    async def run():
        result = await provider.generate(
            [{"role": "user", "content": "Inspect"}],
            [],
            emit=lambda *args, events=emitted: events.append(args),
            cancelled=lambda: False,
            continuation={},
        )
        assert result.provider_fields == {
            "reasoning_content": "private protocol continuation"
        }
        assert result.content == ""
        assert result.calls[0]["id"] == "c1"
        await provider.generate(
            [
                {
                    "role": "assistant",
                    "content": None,
                    **result.provider_fields,
                    "tool_calls": result.calls,
                }
            ],
            [],
            emit=lambda *args, events=emitted: events.append(args),
            cancelled=lambda: False,
            continuation={},
        )

    asyncio.run(run())
    assert (
        captured[-1]["messages"][0]["reasoning_content"]
        == "private protocol continuation"
    )
    assert "private protocol" not in str(emitted)


def test_partial_visible_output_is_never_invisibly_retried(monkeypatch):
    captured, emitted = [], []
    install(
        monkeypatch, [{"choices": [{"delta": {"content": "Partial answer"}}]}], captured
    )
    provider = HTTPProvider(
        {"llmApiBaseUrl": "https://example.test/v1", "llmModel": "test"}
    )
    with pytest.raises(AiRuntimeError, match="before completion"):
        asyncio.run(
            provider.generate(
                [],
                [],
                emit=lambda *args, events=emitted: events.append(args),
                cancelled=lambda: False,
                continuation={},
            )
        )
    assert len(captured) == 1
    assert [(kind, payload) for kind, payload in emitted if kind != "model_timing"] == [
        ("message_delta", {"content": "Partial answer"})
    ]


def test_responses_stream_preserves_tool_identity_and_continuation(monkeypatch):
    captured, emitted = [], []
    install(
        monkeypatch,
        [
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "call_id": "call-responses",
                    "name": "inspect",
                    "arguments": "",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "delta": "{}",
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "response-1",
                    "output": [],
                    "usage": {"input_tokens": 10, "output_tokens": 4},
                },
            },
        ],
        captured,
    )
    provider = HTTPProvider(
        {
            "llmApiBaseUrl": "https://example.test/v1",
            "llmModel": "test",
            "adapter": "responses",
        }
    )
    messages = [
        {"role": "system", "content": "Policy"},
        {"role": "user", "content": "Inspect"},
    ]
    first = asyncio.run(
        provider.generate(
            messages,
            [],
            emit=lambda *args, events=emitted: events.append(args),
            cancelled=lambda: False,
            continuation={},
        )
    )
    assert first.calls[0]["id"] == "call-responses"
    messages += [
        {"role": "assistant", "content": None, "tool_calls": first.calls},
        {"role": "tool", "tool_call_id": "call-responses", "content": "Evidence"},
    ]
    install(
        monkeypatch,
        [
            {"type": "response.output_text.delta", "delta": "Sourced answer"},
            {
                "type": "response.completed",
                "response": {"id": "response-2", "output": []},
            },
        ],
        captured,
    )
    second = asyncio.run(
        provider.generate(
            messages,
            [],
            emit=lambda *args, events=emitted: events.append(args),
            cancelled=lambda: False,
            continuation=first.continuation,
        )
    )
    assert captured[-1]["previous_response_id"] == "response-1"
    assert captured[-1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call-responses",
            "output": "Evidence",
        }
    ]
    assert second.content == "Sourced answer"
    assert [(kind, payload) for kind, payload in emitted if kind != "model_timing"] == [
        ("message_delta", {"content": "Sourced answer"})
    ]

    # Compaction, changed guidance, or an edited prefix must force full input.
    messages[1] = {"role": "user", "content": "Changed compacted history"}
    asyncio.run(
        provider.generate(
            messages,
            [],
            emit=lambda *args: None,
            cancelled=lambda: False,
            continuation=first.continuation,
        )
    )
    assert "previous_response_id" not in captured[-1]
    assert any(
        item.get("content") == "Changed compacted history"
        for item in captured[-1]["input"]
    )


def test_public_reasoning_summary_is_separate_from_private_protocol_content(
    monkeypatch,
):
    captured, emitted = [], []
    install(
        monkeypatch,
        [
            {"type": "response.output_item.added", "item": {"type": "reasoning"}},
            {
                "type": "response.completed",
                "response": {
                    "id": "r1",
                    "output": [
                        {
                            "type": "reasoning",
                            "encrypted_content": "private-opaque",
                            "summary": [
                                {
                                    "type": "summary_text",
                                    "text": "Checked the requested metric definition.",
                                }
                            ],
                        }
                    ],
                },
            },
        ],
        captured,
    )
    asyncio.run(
        HTTPProvider(
            {
                "adapter": "responses",
                "llmApiBaseUrl": "https://example.test/v1",
                "llmModel": "test",
            }
        ).generate(
            [],
            [],
            emit=lambda *args, events=emitted: events.append(args),
            cancelled=lambda: False,
            continuation={},
        )
    )
    summaries = [payload for kind, payload in emitted if kind == "reasoning_summary"]
    assert summaries[-1]["message"] == "Checked the requested metric definition."
    assert summaries[-1]["completed"] is True
    assert "private-opaque" not in json.dumps(emitted)


def test_thinking_status_requires_actual_reasoning_output(monkeypatch):
    for reasoning in [False, True]:
        emitted = []
        events = (
            [{"choices": [{"delta": {"reasoning_content": "private-thought"}}]}]
            if reasoning
            else []
        )
        events.append(
            {"choices": [{"delta": {"content": "Answer"}, "finish_reason": "stop"}]}
        )
        install(monkeypatch, events, [])
        asyncio.run(
            HTTPProvider(
                {"llmApiBaseUrl": "https://example.test/v1", "llmModel": "test"}
            ).generate(
                [],
                [],
                emit=lambda *args, events=emitted: events.append(args),
                cancelled=lambda: False,
                continuation={},
            )
        )
        assert any(kind == "reasoning_status" for kind, _ in emitted) is reasoning
        assert "private-thought" not in json.dumps(emitted)


def test_streamed_summary_updates_are_batched_and_reconciled(monkeypatch):
    emitted, captured = [], []
    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": "rs1", "type": "reasoning"},
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "rs1",
            "summary_index": 0,
            "delta": "Checking ",
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "rs1",
            "summary_index": 0,
            "delta": "datasets.",
        },
        {
            "type": "response.completed",
            "response": {
                "id": "r1",
                "output": [
                    {
                        "id": "rs1",
                        "type": "reasoning",
                        "summary": [
                            {"type": "summary_text", "text": "Checked datasets."}
                        ],
                    }
                ],
            },
        },
    ]
    install(monkeypatch, events, captured)
    original = Response.aiter_lines

    async def delayed(self):
        pause = False
        async for line in original(self):
            yield line
            if "Checking " in line:
                pause = True
            if not line and pause:
                await asyncio.sleep(0.2)
                pause = False

    monkeypatch.setattr(Response, "aiter_lines", delayed)

    async def run():
        provider = HTTPProvider(
            {"adapter": "responses", "llmApiBaseUrl": "https://example.test/v1"}
        )
        for _ in range(2):
            await provider.generate(
                [],
                [],
                emit=lambda kind, value: emitted.append((kind, value)),
                cancelled=lambda: False,
                continuation={},
            )

    asyncio.run(run())
    summaries = [value for kind, value in emitted if kind == "reasoning_summary"]
    assert any(
        value["message"] == "Checking " and not value["completed"]
        for value in summaries
    )
    assert summaries[-1]["message"] == "Checked datasets."
    assert {value["summary_id"] for value in summaries} == {"rs1:0"}
    assert len({value["generation_id"] for value in summaries}) == 2


def test_partial_public_summary_prevents_transport_retry(monkeypatch):
    captured, emitted = [], []
    install(
        monkeypatch,
        [
            {
                "type": "response.reasoning_summary_text.delta",
                "item_id": "rs1",
                "summary_index": 0,
                "delta": "Checking datasets.",
            },
        ],
        captured,
    )
    original = Response.aiter_lines

    async def broken(self):
        async for line in original(self):
            yield line
        raise httpx.ReadTimeout("private transport details")

    monkeypatch.setattr(Response, "aiter_lines", broken)
    with pytest.raises(AiRuntimeError):
        asyncio.run(
            HTTPProvider(
                {"adapter": "responses", "llmApiBaseUrl": "https://example.test/v1"}
            ).generate(
                [],
                [],
                emit=lambda kind, value: emitted.append((kind, value)),
                cancelled=lambda: False,
                continuation={},
            )
        )
    assert len(captured) == 1
    assert any(kind == "reasoning_summary" for kind, _ in emitted)
    assert emitted[-1][1]["status"] == "interrupted"


@pytest.mark.parametrize(
    "provider,enabled,visible",
    [
        ("custom", True, True),
        ("custom", False, False),
        ("openai", True, False),
        ("lmstudio", True, True),
    ],
)
@pytest.mark.parametrize("reasoning_field", ["reasoning_content", "reasoning"])
def test_model_reasoning_display_requires_opt_in_compatible_connection(
    monkeypatch, provider, enabled, visible, reasoning_field
):
    emitted, captured = [], []
    install(
        monkeypatch,
        [
            {"choices": [{"delta": {reasoning_field: "Model reasoning text"}}]},
            {
                "choices": [{"delta": {"content": "Answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            },
        ],
        captured,
    )
    result = asyncio.run(
        HTTPProvider(
            {
                "llmProvider": provider,
                "showModelReasoning": enabled,
                "llmApiBaseUrl": "https://example.test/v1",
            }
        ).generate(
            [],
            [],
            emit=lambda kind, payload: emitted.append((kind, payload)),
            cancelled=lambda: False,
            continuation={},
        )
    )
    reasoning = [p for kind, p in emitted if kind == "model_reasoning"]
    assert bool(reasoning) is visible
    if visible:
        assert reasoning[-1]["message"] == "Model reasoning text"
        assert reasoning[-1]["completed"]
    assert result.provider_fields["reasoning_content"] == "Model reasoning text"
    timing = next(p for kind, p in emitted if kind == "model_timing")
    assert timing["reasoning_characters"] == 20
    assert timing["answer_characters"] == 6
    assert timing["usage"]["prompt_tokens"] == 100
    assert timing["status"] == "completed"
    assert "Model reasoning text" not in json.dumps(timing)

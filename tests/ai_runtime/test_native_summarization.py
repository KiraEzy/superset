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
"""Durable summary and pinned public SDK filter contracts."""

import asyncio
import importlib
from types import SimpleNamespace

import httpx
import pytest
import test_native_sdk as n
from agents import Agent, OpenAIChatCompletionsModel, RunConfig, Runner
from agents.run import ModelInputData
from openai import AsyncOpenAI
from test_native_sdk import database as shared_database

from superset.utils import json

database = shared_database


def test_pinned_sdk_awaits_async_filter_without_persisting_filtered_view(database):
    seen = []

    async def handler(request):
        seen.append(request.read().decode())
        return n.streamed_response()

    async def exercise():
        async def prepare(data):
            await asyncio.sleep(0)
            return ModelInputData(
                input=[{"role": "user", "content": "filtered-view"}],
                instructions=data.model_data.instructions,
            )

        session = n.session(database)
        client = AsyncOpenAI(
            api_key="test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        try:
            result = Runner.run_streamed(
                Agent(
                    name="contract", model=OpenAIChatCompletionsModel("test", client)
                ),
                "original",
                session=session,
                run_config=RunConfig(
                    call_model_input_filter=prepare, tracing_disabled=True
                ),
            )
            async for _ in result.stream_events():
                pass
            assert result.final_output == "Datasets available."
            saved = await session.get_items()
            assert saved[0]["content"] == "original"
            assert "filtered-view" not in json.dumps(saved)
        finally:
            await client.close()

    asyncio.run(exercise())
    assert "filtered-view" in seen[0]
    assert "original" not in seen[0]


summary_module = importlib.import_module(f"{n.t.PACKAGE}.native_summarization")


def memory():
    result = {key: [] for key in summary_module.FIELDS}
    result["constraints"] = ["Keep the map blue"]
    result["references"] = ["chart-42", "evidence-7"]
    result["write_outcomes"] = ["chart-42 creation completed; do not repeat"]
    return result


class Client:
    def __init__(self, response=None, hook=None):
        self.chat = SimpleNamespace(completions=self)
        self.requests = []
        self.response = response or json.dumps(memory())
        self.hook = hook

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.hook:
            self.hook()
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop", message=SimpleNamespace(content=self.response)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=100),
        )


def history():
    items = []
    for i in range(5):
        items += [
            {
                "role": "user",
                "content": f"Request {i}: " + "old visible history " * 220,
            },
            {"role": "assistant", "content": "Answer " * 200},
        ]
    return items


def summarizer(database, client, **kwargs):
    return summary_module.Summarizer(
        n.session(database),
        client,
        {"llmModel": "test", "llmProvider": "deepseek"},
        5000,
        lambda: None,
        lambda: 120,
        **kwargs,
    )


def test_durable_summary_reuse_preserves_full_history(database):
    async def exercise():
        original = history()
        session = n.session(database)
        await session.add_items(original)
        client = Client()
        first = summarizer(database, client)
        view = await first.prepare(original, "system", [])
        assert summary_module.request_cost(
            {"input": view}
        ) < summary_module.request_cost({"input": original})
        assert "Keep the map blue" in json.dumps(view)
        assert view[-2:] == original[-2:]
        assert await session.get_items() == original
        assert len(client.requests) > 0
        for request in client.requests:
            assert "tools" not in request
            assert request["extra_body"] == {"thinking": {"type": "disabled"}}
        count = len(client.requests)
        second = summarizer(database, client)
        assert await second.prepare(original, "system", []) == view
        assert len(client.requests) == count

    asyncio.run(exercise())


def test_summary_invalidates_on_prefix_edit_and_model_binding(database):
    async def exercise():
        original = history()
        await n.session(database).add_items(original)
        client = Client()
        service = summarizer(database, client)
        await service.prepare(original, "system", [])
        count = len(client.requests)
        edited = [dict(v) for v in original]
        edited[0]["content"] = "Different goal " * 300
        await service.prepare(edited, "system", [])
        assert len(client.requests) > count
        other = n.session(database)
        other.binding = "new-model"
        other.allow_rebind = True
        assert other.summary_snapshot()[1] is None

    asyncio.run(exercise())


def test_summary_compare_and_swap_rejects_stale_work(database):
    async def exercise():
        session = n.session(database)
        await session.add_items(history())
        revision, _ = session.summary_snapshot()
        await n.session(database).add_items(
            [{"role": "user", "content": "new revision"}]
        )
        value = {
            "boundary": 2,
            "fingerprint": "x" * 64,
            "policy_version": 1,
            "summary": memory(),
        }
        assert session.save_summary(revision, value) is False
        assert session.summary_snapshot()[1] is None

    asyncio.run(exercise())


@pytest.mark.parametrize("response", ["not json", "{}", '{"goals": "bad"}'])
def test_malformed_summary_falls_back_without_history_mutation(database, response):
    async def exercise():
        original = history()
        await n.session(database).add_items(original)
        service = summarizer(database, Client(response))
        assert await service.prepare(original, "system", []) == original
        assert await service.session.get_items() == original

    asyncio.run(exercise())


def test_timeout_and_cancellation_do_not_publish(database):
    async def exercise():
        original = history()
        await n.session(database).add_items(original)
        service = summarizer(database, Client())
        service.remaining = lambda: 0
        assert await service.prepare(original, "system", []) == original
        assert service.session.summary_snapshot()[1] is None

        def cancelled():
            raise summary_module.AiRuntimeError("cancelled", code="cancelled")

        service.check = cancelled
        with pytest.raises(summary_module.AiRuntimeError):
            await service.prepare(original, "system", [])

    asyncio.run(exercise())


def test_active_batch_compacts_durably_but_keeps_pending_protocol(database):
    async def exercise():
        original = [{"role": "user", "content": "Keep this current request"}]
        for i in range(5):
            original += [
                {"type": "reasoning", "summary": [{"text": "secret reasoning" * 100}]},
                {
                    "type": "function_call",
                    "call_id": str(i),
                    "name": "read",
                    "arguments": "{}",
                },
                {
                    "type": "function_call_output",
                    "call_id": str(i),
                    "output": "evidence " * 200,
                },
            ]
        original += [
            {
                "type": "function_call",
                "call_id": "pending",
                "name": "read",
                "arguments": "{}",
            }
        ]
        session = n.session(database)
        await session.add_items(original)
        client = Client()
        view = await summarizer(database, client).prepare(original, "system", [])
        assert original[0] in view
        assert view[-1] == original[-1]
        assert "secret reasoning" not in json.dumps(client.requests)
        count = len(client.requests)
        assert (
            await summarizer(database, client).prepare(original, "system", []) == view
        )
        assert len(client.requests) == count
        assert await session.get_items() == original

    asyncio.run(exercise())


def test_projection_omits_private_content_preserves_image_ids():
    values = [
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": "data:image/png;base64,SECRET"},
                {"type": "input_image", "image_url": "focal-image:owned"},
            ],
        },
        {"type": "reasoning", "summary": [{"text": "secret thought"}]},
        {
            "type": "function_call_output",
            "call_id": "exact",
            "output": '{"llmApiKey":"secret-key", "chart_id":42}',
            "provider_data": {"hidden": "secret"},
        },
    ]
    text = json.dumps(summary_module.safe_items(values))
    assert "SECRET" not in text
    assert "secret" not in text
    assert "owned" in text
    assert "exact" in text
    assert "42" in text


def test_clear_truncate_and_scope_preserve_checkpoint_boundaries(database):
    async def exercise():
        session = n.session(database)
        await session.add_items(history())
        await summarizer(database, Client()).prepare(history(), "system", [])
        assert session.summary_snapshot()[1]
        with pytest.raises(summary_module.AiRuntimeError):
            n.session(database, owner=999).summary_snapshot()
        await session.truncate(0)
        assert session.summary_snapshot()[1] is None
        await session.add_items(history())
        await summarizer(database, Client()).prepare(history(), "system", [])
        await session.get_items()
        await session.clear_session()
        assert session.summary_snapshot()[1] is None
        assert await session.get_items() == []

    asyncio.run(exercise())


def test_branch_does_not_inherit_source_summary(database):
    history_module = importlib.import_module(f"{n.t.PACKAGE}.native_history")

    async def exercise():
        original = history()
        await n.session(database).add_items(original)
        await summarizer(database, Client()).prepare(original, "system", [])
        history_module.clone_prefix(
            database, n.models, "thread", "branch", 1, 2, len(original), {}
        )
        database.commit()
        model = n.models[0].summary_model
        assert database.query(model).filter_by(session_id="thread").count() == 1
        assert database.query(model).filter_by(session_id="branch").count() == 0

    asyncio.run(exercise())


def test_scope_post_and_lease_rechecked_before_publication(database):
    async def exercise():
        session = n.session(database)
        await session.add_items(history())
        revision, _ = session.summary_snapshot()
        value = {
            "boundary": 2,
            "fingerprint": "x" * 64,
            "policy_version": 1,
            "summary": memory(),
        }
        session.post_id = 999
        with pytest.raises(summary_module.AiRuntimeError):
            session.save_summary(revision, value)
        session.post_id = 2

        def expired():
            raise summary_module.AiRuntimeError("Lease expired", code="lease_lost")

        session.guard = expired
        with pytest.raises(summary_module.AiRuntimeError):
            session.save_summary(revision, value)

    asyncio.run(exercise())


def test_pending_batches_are_not_selected_as_compaction_boundaries():
    assert (
        summary_module.boundaries(
            [
                {"role": "user", "content": "first"},
                {"type": "function_call", "call_id": "unresolved"},
                {"role": "user", "content": "must not cut across pending call"},
            ]
        )
        == []
    )


def test_summary_generation_failure_reuses_previous_valid_checkpoint(database):
    async def exercise():
        original = history()
        await n.session(database).add_items(original)
        service = summarizer(database, Client())
        first = await service.prepare(original, "system", [])
        more = original + history()
        await service.session.add_items(history())
        service.client = Client("invalid")
        result = await service.prepare(more, "system", [])
        assert result[: len(first)] == first
        assert result[-len(history()) :] == history()

    asyncio.run(exercise())


def test_failed_compaction_is_not_retried_in_later_tool_rounds(database):
    async def exercise():
        original = history()
        await n.session(database).add_items(original)
        client = Client("invalid")
        service = summarizer(database, client)
        assert await service.prepare(original, "system", []) == original
        attempts = len(client.requests)
        assert attempts == 1
        assert await service.prepare(original, "system", []) == original
        assert len(client.requests) == attempts
        # A fresh run/turn may retry on the same provider without changing settings.
        await summarizer(database, client).prepare(original, "system", [])
        assert len(client.requests) == attempts + 1

    asyncio.run(exercise())

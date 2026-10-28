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
"""Scoped branch prefixes, session concurrency and terminal protocol repair."""

import asyncio
import importlib
from types import SimpleNamespace
from typing import Any

import pytest
import test_native_sdk as n
from test_native_sdk import database as shared_database

from superset.utils import json

history = importlib.import_module(f"{n.t.PACKAGE}.native_history")


database = shared_database


def test_stale_session_cannot_append_over_new_revision(database: Any) -> None:
    async def exercise() -> None:
        stale = n.session(database)
        await stale.get_items()
        writer = n.session(database)
        await writer.add_items([{"role": "user", "content": "new"}])
        with pytest.raises(n.t.contracts.AiRuntimeError, match="concurrently"):
            await stale.add_items([{"role": "user", "content": "stale"}])
        assert len(await writer.get_items()) == 1

    asyncio.run(exercise())


def test_branch_copies_only_complete_prefix_and_remaps_artifacts(database: Any) -> None:
    async def exercise() -> None:
        source = n.session(database)
        await source.add_items(
            [
                {"role": "user", "content": "original"},
                {
                    "type": "function_call",
                    "call_id": "call",
                    "name": "read_artifact",
                    "arguments": json.dumps({"artifact_id": "old"}),
                },
                {
                    "type": "function_call_output",
                    "call_id": "call",
                    "output": json.dumps({"id": "old"}),
                },
                {"role": "assistant", "content": "answer"},
                {"role": "user", "content": "excluded"},
            ]
        )
        history.clone_prefix(
            database, n.models, "thread", "branch", 1, 2, 4, {"old": {"id": "new"}}
        )
        database.commit()
        target = n.storage.FocalSession(
            "branch",
            database=database,
            models=n.models,
            owner_id=1,
            post_id=2,
            binding="model",
            turn_id="branch-turn",
            guard=lambda: None,
        )
        values = await target.get_items()
        assert len(values) == 4
        assert json.loads(values[1]["arguments"])["artifact_id"] == "new"
        assert json.loads(values[2]["output"])["id"] == "new"
        assert (await source.get_items())[-1]["content"] == "excluded"

    asyncio.run(exercise())


@pytest.mark.parametrize("known", [True, False])
def test_terminal_history_closes_orphan_calls_without_reexecution(
    database: Any, known: bool
) -> None:
    async def exercise() -> None:
        source = n.session(database)
        await source.add_items(
            [
                {"role": "user", "content": "change"},
                {
                    "type": "function_call",
                    "call_id": "call",
                    "name": "write",
                    "arguments": "{}",
                },
            ]
        )
        cp = {
            "sdk_session_id": "thread",
            "calls": {
                "call": {
                    "status": "completed" if known else "in_progress",
                    "result": {"saved": True},
                }
            },
        }
        history.seal_terminal(
            database, n.models, SimpleNamespace(id="turn", user_id=1, post_id=2), cp
        )
        database.commit()
        values = await source.get_items()
        assert values[-1]["type"] == "function_call_output"
        if known:
            assert json.loads(values[-1]["output"])["result"]["saved"]
        else:
            assert "without a recorded outcome" in values[-1]["output"]

    asyncio.run(exercise())


def test_model_rebind_requires_scope_and_a_new_run(database: Any) -> None:
    async def exercise() -> None:
        await n.session(database).add_items([{"role": "user", "content": "kept"}])
        args = {
            "database": database,
            "models": n.models,
            "owner_id": 1,
            "post_id": 2,
            "binding": "different-model",
            "turn_id": "new",
            "guard": lambda: None,
        }
        with pytest.raises(n.t.contracts.AiRuntimeError, match="Model changed"):
            await n.storage.FocalSession("thread", **args).get_items()
        switched = n.storage.FocalSession("thread", allow_rebind=True, **args)
        assert (await switched.get_items())[0]["content"] == "kept"

    asyncio.run(exercise())


@pytest.mark.parametrize("mutation", ["pop_item", "clear_session", "truncate"])
def test_stale_destructive_session_mutations_conflict(
    database: Any, mutation: str
) -> None:
    async def exercise() -> None:
        first = n.session(database)
        await first.add_items([{"role": "user", "content": "first"}])
        stale = n.session(database, turn="stale")
        await stale.get_items()
        await first.add_items([{"role": "assistant", "content": "newer"}])
        with pytest.raises(n.t.contracts.AiRuntimeError, match="concurrently"):
            await getattr(stale, mutation)(*([0] if mutation == "truncate" else []))
        assert len(await first.get_items()) == 2

    asyncio.run(exercise())


def test_image_validation_uses_scoped_sdk_items(database: Any) -> None:
    async def exercise() -> None:
        source = n.session(database)
        await source.add_items(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": "focal-image:private"}
                    ],
                }
            ]
        )
        assert history.image_reference_projection(database, n.models, "thread", 1, 2)[
            0
        ]["content"] == [{"type": "image_ref", "image_id": "private"}]
        assert (
            history.image_reference_projection(database, n.models, "thread", 9, 2) == []
        )

    asyncio.run(exercise())

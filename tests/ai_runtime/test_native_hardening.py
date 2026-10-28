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
"""SDK-native durable approval and operation recovery contracts."""

import asyncio
import copy
from typing import Any

import httpx
import pytest
import test_native_sdk as n
from test_native_sdk import database as shared_database

database = shared_database


def setup_run(database: Any) -> tuple[Any, ...]:
    checkpoints: list[Any] = []
    requests: list[Any] = []
    events: list[Any] = []
    tool = n.t.contracts.Tool(
        "datasets",
        "write_resource",
        {"id": "private"},
        {"type": "object", "properties": {}},
        "Change resource",
        effect="write",
    )
    pool = n.t.Pool([tool], checkpoints)

    async def handler(request: Any) -> Any:
        requests.append(request)
        return n.streamed_response(call=len(requests) == 1)

    def state(cp: Any = None) -> dict[str, Any]:
        session = n.session(database, turn="accepted")
        session.offset = (cp or {}).get("session_offset", 0)
        return {
            "execution_version": 3,
            "execution_sdk_version": "0.10.5",
            "config": {
                "llmApiBaseUrl": "https://provider.test/v1",
                "llmModel": "deepseek-test",
                "llmProvider": "deepseek",
            },
            "input_text": "Perform the requested operation",
            "checkpoint": cp or {},
            "_native_session": session,
            "_native_transport": httpx.MockTransport(handler),
            "_mcp_pool": pool,
            "budgets": {"context_window_tokens": 100000},
        }

    async def run(value: Any, persist: Any = checkpoints.append, **kwargs: Any) -> Any:
        return await n.native.run_native(
            value,
            emit=lambda k, p: events.append((k, p)),
            checkpoint=persist,
            cancelled=lambda: False,
            refresh_auth=lambda: "token",
            **kwargs,
        )

    return checkpoints, requests, events, pool, state, run


@pytest.mark.parametrize("decision", ["accept", "decline"])
def test_approval_round_trip_does_not_duplicate_input(
    database: Any, decision: str
) -> None:
    checkpoints, requests, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        waiting = await run(state())
        assert waiting["status"] == "waiting_approval"
        assert not pool.invocations
        accepted = state(waiting["checkpoint"])
        accepted["pending_response"] = {"decision": decision}
        if decision == "accept":
            accepted["approved_scopes"] = [waiting["pending_request"]["fingerprint"]]
        result = await run(accepted)
        assert result["status"] == "completed"
        assert len(pool.invocations) == (1 if decision == "accept" else 0)
        saved = await accepted["_native_session"].get_items()
        assert sum(i.get("role") == "user" for i in saved) == 1
        calls = [i["call_id"] for i in saved if i.get("type") == "function_call"]
        outputs = [
            i["call_id"] for i in saved if i.get("type") == "function_call_output"
        ]
        assert len(calls) == len(set(calls)) == 1
        assert outputs == calls

    asyncio.run(exercise())
    assert len(requests) == 2


def test_completed_write_is_reused_after_checkpoint_interruption(database: Any) -> None:
    checkpoints, _, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        waiting = await run(state())
        accepted = state(waiting["checkpoint"])
        accepted["pending_response"] = {"decision": "accept"}
        accepted["approved_scopes"] = [waiting["pending_request"]["fingerprint"]]
        crashed = False

        def persist(cp: Any) -> None:
            nonlocal crashed
            checkpoints.append(copy.deepcopy(cp))
            if not crashed and any(
                r.get("status") == "completed" for r in cp["calls"].values()
            ):
                crashed = True
                raise RuntimeError("Simulated worker loss after durable outcome")

        with pytest.raises(n.t.contracts.AiRuntimeError):
            await run(accepted, persist)
        retry = state(checkpoints[-1])
        retry["approved_scopes"] = accepted["approved_scopes"]
        result = await run(retry)
        assert result["status"] == "completed"
        assert len(pool.invocations) == 1

    asyncio.run(exercise())


def test_unknown_write_outcome_is_not_retried(database: Any) -> None:
    checkpoints, _, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        waiting = await run(state())
        accepted = state(waiting["checkpoint"])
        accepted["pending_response"] = {"decision": "accept"}
        accepted["approved_scopes"] = [waiting["pending_request"]["fingerprint"]]
        pool.fail = True
        with pytest.raises(n.t.contracts.AiRuntimeError):
            await run(accepted)
        retry = state(checkpoints[-1])
        retry["approved_scopes"] = accepted["approved_scopes"]
        with pytest.raises(n.t.contracts.AiRuntimeError):
            await run(retry)
        assert len(pool.invocations) == 1

    asyncio.run(exercise())


def test_changed_schema_requires_a_fresh_approval(database: Any) -> None:
    _, _, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        waiting = await run(state())
        old = waiting["pending_request"]["fingerprint"]
        pool.tools[0].schema["additionalProperties"] = False
        accepted = state(waiting["checkpoint"])
        accepted.update(pending_response={"decision": "accept"}, approved_scopes=[old])
        changed = await run(accepted)
        assert changed["status"] == "waiting_approval"
        assert changed["pending_request"]["fingerprint"] != old
        assert not pool.invocations

    asyncio.run(exercise())


def test_permission_revocation_is_checked_after_approval(database: Any) -> None:
    _, _, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        waiting = await run(state())
        accepted = state(waiting["checkpoint"])
        accepted.update(
            pending_response={"decision": "accept"},
            approved_scopes=[waiting["pending_request"]["fingerprint"]],
        )

        def deny(name: str) -> None:
            raise n.t.contracts.AiRuntimeError("Permission revoked", code="tool_denied")

        accepted["_authorize_tool"] = deny
        with pytest.raises(n.t.contracts.AiRuntimeError, match="revoked"):
            await run(accepted)
        assert not pool.invocations

    asyncio.run(exercise())


def test_clarification_resumes_same_sdk_call(database: Any) -> None:
    _, requests, _, pool, state, run = setup_run(database)

    async def handler(request: Any) -> Any:
        requests.append(request)
        return n.streamed_response(
            call=len(requests) == 1,
            name="ask_user",
            arguments={"question": "Which region?"},
        )

    async def exercise() -> None:
        initial = state()
        initial["_native_transport"] = httpx.MockTransport(handler)
        waiting = await run(initial)
        assert waiting["status"] == "waiting_input"
        accepted = state(waiting["checkpoint"])
        accepted["_native_transport"] = httpx.MockTransport(handler)
        accepted["pending_response"] = {"input": "Kowloon"}
        result = await run(accepted)
        assert result["status"] == "completed"
        assert not pool.invocations
        assert (
            sum(
                i.get("role") == "user"
                for i in await accepted["_native_session"].get_items()
            )
            == 1
        )
        assert b"Kowloon" in requests[-1].content

    asyncio.run(exercise())


def test_steering_rejects_pending_writes_before_new_guidance(database: Any) -> None:
    checkpoints, requests, _, pool, state, run = setup_run(database)
    delivered = False

    def consume() -> list[Any]:
        nonlocal delivered
        if len(requests) == 1 and not delivered:
            delivered = True
            return [
                {
                    "input": "Do not change anything; explain only",
                    "_native_input_id": "steer",
                }
            ]
        return []

    async def exercise() -> None:
        result = await run(state(), consume_inputs=consume)
        assert result["status"] == "queued"
        assert not pool.invocations
        resumed = await run(state(checkpoints[-1]))
        assert resumed["status"] == "completed"
        assert not pool.invocations
        saved = await state(checkpoints[-1])["_native_session"].get_items()
        assert sum(i.get("role") == "user" for i in saved) == 2
        assert b"Do not change anything" in requests[-1].content

    asyncio.run(exercise())


def test_connection_repair_resumes_unexecuted_approved_call(database: Any) -> None:
    checkpoints, _, _, pool, state, run = setup_run(database)
    original = pool.call
    attempted = 0

    async def disconnected(*args: Any, **kwargs: Any) -> Any:
        nonlocal attempted
        attempted += 1
        if attempted == 1:
            raise n.t.contracts.AiRuntimeError(
                "Account needs repair", code="connection_auth"
            )
        return await original(*args, **kwargs)

    pool.call = disconnected

    async def exercise() -> None:
        waiting = await run(state())
        accepted = state(waiting["checkpoint"])
        accepted.update(
            pending_response={"decision": "accept"},
            approved_scopes=[waiting["pending_request"]["fingerprint"]],
        )
        with pytest.raises(n.t.contracts.AiRuntimeError, match="repair"):
            await run(accepted)
        repaired = state(copy.deepcopy(checkpoints[-1]))
        repaired["approved_scopes"] = accepted["approved_scopes"]
        result = await run(repaired)
        assert result["status"] == "completed"
        assert len(pool.invocations) == 1
        assert (
            sum(
                item.get("role") == "user"
                for item in await repaired["_native_session"].get_items()
            )
            == 1
        )

    asyncio.run(exercise())


def test_dispatch_gate_bounds_reads_excludes_writes_and_stops_failed_batch() -> None:
    async def exercise() -> None:
        gate = n.native.DispatchGate(limit=2)
        active = 0
        peak = 0

        async def read() -> None:
            nonlocal active, peak
            async with gate.enter(True):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        async def write() -> None:
            async with gate.enter(False):
                assert active == 0
                await asyncio.sleep(0.01)
                assert active == 0

        await asyncio.gather(read(), read(), read(), write(), read())
        assert peak == 2
        with pytest.raises(ValueError, match="effect outcome unknown"):
            async with gate.enter(False):
                raise ValueError("effect outcome unknown")
        with pytest.raises(n.t.contracts.AiRuntimeError, match="batch stopped"):
            async with gate.enter(False):
                pytest.fail("must not dispatch")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "decisions", [("accept", "accept"), ("decline", "accept"), ("accept", "decline")]
)
def test_batch_decisions_survive_sequential_approval_resumes(
    database: Any, decisions: tuple[str, str]
) -> None:
    _, _, _, pool, state, run = setup_run(database)
    pool.tools[0].schema["properties"] = {"id": {"type": "integer"}}
    requests: list[Any] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) != 1:
            return n.streamed_response()
        original = n.streamed_response(call=True, arguments={"id": 1})
        lines = []
        for line in original.content.decode().splitlines():
            if line.startswith("data: {"):
                chunk = n.json.loads(line[6:])
                calls = chunk["choices"][0]["delta"].get("tool_calls", [])
                if calls and calls[0].get("id"):
                    calls.append(
                        {
                            "index": 1,
                            "id": "call-2",
                            "type": "function",
                            "function": {"name": "datasets", "arguments": '{"id":2}'},
                        }
                    )
                    line = "data: " + n.json.dumps(chunk)
            lines.append(line)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=("\n".join(lines) + "\n").encode(),
        )

    def resumed(checkpoint: Any = None) -> dict[str, Any]:
        value = state(copy.deepcopy(checkpoint))
        value["_native_transport"] = httpx.MockTransport(handler)
        return value

    async def exercise() -> None:
        result = await run(resumed())
        for index, decision in enumerate(decisions, 1):
            assert result["status"] == "waiting_approval"
            pending = result["pending_request"]
            assert pending["call_id"] == f"call-{index}"
            assert not pool.invocations
            assert len(requests) == 1
            value = resumed(result["checkpoint"])
            value["pending_response"] = {"decision": decision}
            if decision == "accept":
                value["approved_scopes"] = [pending["fingerprint"]]
            result = await run(value)
        assert result["status"] == "completed"
        assert pool.invocations == [
            ("datasets", {"id": index})
            for index, decision in enumerate(decisions, 1)
            if decision == "accept"
        ]
        saved = await value["_native_session"].get_items()
        assert {
            item["call_id"]
            for item in saved
            if item.get("type") == "function_call_output"
        } == {"call-1", "call-2"}

    asyncio.run(exercise())
    assert len(requests) == 2


@pytest.mark.parametrize("effect", ["unknown", "write", "destructive"])
def test_full_access_skips_routine_confirmation_but_checks_authorization(
    database: Any, effect: str
) -> None:
    _, _, _, pool, state, run = setup_run(database)
    pool.tools[0].effect = effect
    authorized: list[str] = []

    async def exercise() -> None:
        value = state()
        value["approval_mode"] = "full_access"
        value["_authorize_tool"] = authorized.append
        result = await run(value)
        assert result["status"] == "completed"
        assert pool.invocations == [("datasets", {})]
        assert authorized == ["write_resource"]

    asyncio.run(exercise())


def test_full_access_preserves_unknown_write_outcome_protection(database: Any) -> None:
    checkpoints, _, _, pool, state, run = setup_run(database)
    pool.fail = True

    async def exercise() -> None:
        value = state()
        value["approval_mode"] = "full_access"
        with pytest.raises(n.t.contracts.AiRuntimeError, match="transport"):
            await run(value)
        retry = state(checkpoints[-1])
        retry["approval_mode"] = "full_access"
        with pytest.raises(n.t.contracts.AiRuntimeError, match="review"):
            await run(retry)
        assert len(pool.invocations) == 1

    asyncio.run(exercise())


def test_full_access_does_not_bypass_tool_permissions(database: Any) -> None:
    _, _, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        value = state()
        value["approval_mode"] = "full_access"

        def deny(name: str) -> None:
            raise n.t.contracts.AiRuntimeError(
                "Permission revoked", code="permission_revoked"
            )

        value["_authorize_tool"] = deny
        with pytest.raises(n.t.contracts.AiRuntimeError, match="Permission revoked"):
            await run(value)
        assert pool.invocations == []

    asyncio.run(exercise())


def test_refresh_revalidates_pending_proposal_without_approving(database: Any) -> None:
    _, requests, _, pool, state, run = setup_run(database)

    async def exercise() -> None:
        waiting = await run(state())
        value = state(waiting["checkpoint"])
        value["pending_response"] = {"decision": "refresh"}
        refreshed = await run(value)
        assert refreshed["status"] == "waiting_approval"
        assert (
            refreshed["pending_request"]["call_id"]
            == waiting["pending_request"]["call_id"]
        )
        assert pool.invocations == []
        assert len(requests) == 1

    asyncio.run(exercise())

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
"""SDK-native execution with scoped approvals, sessions and recovery boundaries."""

from __future__ import annotations

import asyncio
import copy
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any
from uuid import uuid4

from agents import Agent, FunctionTool, ModelSettings, RunConfig, Runner, RunState
from agents.exceptions import AgentsException
from agents.tool import Tool as SDKTool
from openai import APIError

from superset.utils import json

from .artifacts import extract_artifacts
from .contracts import (
    AiRuntimeError,
    ASK_USER,
    READ_ARTIFACT,
    READ_EVIDENCE,
    TurnCancelledError,
)
from .evidence import bounded, read_page
from .execution import OPENAI_CLIENT_VERSION, protect_sdk_logs, SDK_VERSION
from .mcp import MCPPool
from .native_approvals import prepare_approvals
from .native_model import context_filter, create_model
from .policy import effect_for, fingerprint, normalized_arguments, validate_arguments

FIND_TOOLS = {
    "function": {
        "name": "find_bi_tools",
        "description": (
            "Search authorized BI tools by name or task. All authorized tools "
            "are already available on every model call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 120}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
}


class DispatchGate:
    """Bound reads and exclude writes; stop later effects after a failed callback."""

    def __init__(self, limit: int = 4) -> None:
        self.condition = asyncio.Condition()
        self.limit = limit
        self.readers = 0
        self.writing = False
        self.waiting_writes = 0
        self.stopped = False

    @asynccontextmanager
    async def enter(self, read: bool) -> Any:
        async with self.condition:
            if not read:
                self.waiting_writes += 1
            try:
                await self.condition.wait_for(
                    lambda: self.stopped
                    or (
                        not self.writing
                        and (
                            self.readers < self.limit and not self.waiting_writes
                            if read
                            else self.readers == 0
                        )
                    )
                )
                if self.stopped:
                    raise AiRuntimeError("Tool batch stopped", code="batch_stopped")
                if read:
                    self.readers += 1
                else:
                    self.writing = True
            finally:
                if not read:
                    self.waiting_writes -= 1
        try:
            yield
        except BaseException:
            self.stopped = True
            raise
        finally:
            async with self.condition:
                if read:
                    self.readers -= 1
                else:
                    self.writing = False
                self.condition.notify_all()


async def run_native(  # noqa: C901 - isolated SDK orchestration and product callbacks
    state: dict[str, Any],
    *,
    emit: Callable[..., None],
    checkpoint: Callable[..., None],
    cancelled: Callable[[], bool],
    refresh_auth: Callable[[], Any],
    consume_inputs: Callable[[], list[dict[str, Any]]] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Run or resume the SDK session under scoped domain and delivery policies."""
    protect_sdk_logs()
    if (
        version("openai-agents") != SDK_VERSION
        or version("openai") != OPENAI_CLIENT_VERSION
    ):
        raise AiRuntimeError("Native SDK dependency mismatch", code="engine_version")
    if (
        state.get("execution_version") != 3
        or state.get("execution_sdk_version") != SDK_VERSION
    ):
        raise AiRuntimeError(
            "Native execution contract mismatch", code="engine_version"
        )
    from .engine import SYSTEM

    started = time.monotonic()
    cp: dict[str, Any] = {
        "native_started": True,
        "calls": {},
        "artifacts": [],
        "tools_used": [],
        "content": "",
        "messages": [],
        "usage": {},
        "active_seconds": 0,
        **copy.deepcopy(state.get("checkpoint") or {}),
    }
    config, budgets = (
        {
            **state["config"],
            "image_user_id": state.get("user_id"),
            "image_post_id": state.get("post_id"),
        },
        state.get("budgets", {}),
    )
    gate = DispatchGate()
    session = state["_native_session"]
    cp["sdk_session_id"] = session.session_id
    prior_active = float(cp.get("active_seconds", 0))
    focused = cp.pop("resume_focus", None) or (
        (cp.get("pending_request") or {}).get("reason") == "context"
        and (state.get("pending_response") or {}).get("input")
    )
    if focused:
        saved = await session.get_items()
        calls = {i["call_id"] for i in saved if i.get("type") == "function_call"}
        outputs = {
            i["call_id"] for i in saved if i.get("type") == "function_call_output"
        }
        if not calls <= outputs:
            raise AiRuntimeError(
                "An unresolved tool call needs review", code="uncertain_write"
            )
        cp["session_start"] = len(saved)
        cp["usage_base"] = dict(cp["usage"])
        cp.pop("sdk_state", None)
        cp["action_input"] = str(focused).strip()
        cp["content"] = ""
        emit("message_reset", {"content": ""})
        state.pop("pending_response", None)
    state["input_text"] = cp.get("action_input", state["input_text"])
    if "session_start" not in cp:
        cp["session_start"] = len(await session.get_items())
    elif not cp.get("sdk_state") and not focused:
        if any(r.get("status") != "completed" for r in cp.get("calls", {}).values()):
            raise AiRuntimeError(
                "Execution checkpoint needs review", code="uncertain_write"
            )
        await session.truncate(cp["session_start"])
        cp["content"] = ""
        emit("message_reset", {"content": ""})

    def check() -> None:
        if cancelled():
            raise TurnCancelledError("Turn cancelled", code="cancelled")
        refresh_auth()

    def persist() -> None:
        cp["active_seconds"] = prior_active + time.monotonic() - started
        cp["session_offset"] = session.offset
        checkpoint(copy.deepcopy(cp))

    def outcome(status: str, request: Any = None) -> dict[str, Any]:
        cp["pending_request"] = request
        persist()
        return {
            "status": status,
            "content": cp["content"],
            "messages": [],
            "checkpoint": cp,
            "tools_used": cp["tools_used"],
            "artifacts": cp["artifacts"],
            "usage": cp["usage"],
            "pending_request": request,
        }

    persist()

    def poll_inputs() -> None:
        if consume_inputs is None:
            return
        for entry in consume_inputs():
            identifier = entry.get("_native_input_id")
            if identifier and identifier in cp.setdefault("input_ids", []):
                continue
            if entry.get("_approval_mode") in {"ask", "full_access"}:
                state["approval_mode"] = entry["_approval_mode"]
            text = entry.get("input")
            if not entry.get("request_id") and isinstance(text, str) and text.strip():
                cp.setdefault("steering", []).append(text.strip())
            if identifier:
                cp.setdefault("input_ids", []).append(identifier)
        persist()
        if state.get("_ack_native_inputs"):
            state["_ack_native_inputs"](cp.get("input_ids", []))

    def before_request() -> None:
        poll_inputs()
        if cp.get("steering"):
            raise AiRuntimeError("New guidance accepted", code="accepted_steering")

    async with state.get("_mcp_pool", MCPPool()) as pool:
        discovered = await pool.discover(state.get("connections", []), refresh_auth)
        tools = [
            t
            for t in discovered
            if (not state.get("_tool_filter") or state["_tool_filter"](t.original_name))
        ]
        cp.pop("selected_tools", None)

        async def dispatch(ctx: Any, raw: str) -> str:  # noqa: C901
            target = next(t for t in tools if t.name == ctx.tool_name)
            preview_args = normalized_arguments(target, json.loads(raw))
            async with gate.enter(effect_for(target, preview_args) == "read"):
                check()
                authorize = state.get("_authorize_tool")
                if authorize:
                    authorize(target.original_name)
                args = normalized_arguments(target, json.loads(raw))
                try:
                    validate_arguments(target.schema, args)
                except AiRuntimeError:
                    return json.dumps(
                        {
                            "isError": True,
                            "message": (
                                "Invalid tool arguments; use the advertised schema"
                            ),
                        }
                    )
                binding = fingerprint(target, args)
                if cp.get("bindings", {}).get(ctx.tool_call_id) != binding:
                    raise AiRuntimeError(
                        "Tool approval changed", code="approval_changed"
                    )
                previous = cp["calls"].get(ctx.tool_call_id)
                if previous:
                    if previous.get("fingerprint") != binding:
                        raise AiRuntimeError(
                            "Operation changed", code="approval_changed"
                        )
                    if previous["status"] == "completed":
                        visible, truncated = bounded(
                            previous["result"], max_chars=10000
                        )
                        return json.dumps(
                            {
                                "result": visible,
                                "truncated": truncated,
                                "evidence_ref": ctx.tool_call_id,
                            }
                        )
                    if (
                        previous["status"] == "in_progress"
                        and previous["effect"] != "read"
                    ):
                        raise AiRuntimeError(
                            "Operation outcome needs review", code="uncertain_write"
                        )
                if len(cp["calls"]) >= int(budgets.get("max_tool_calls", 24)):
                    raise AiRuntimeError("Tool budget reached", code="tool_budget")
                call_id = ctx.tool_call_id
                cp["calls"][call_id] = {
                    "tool": target.name,
                    "arguments": args,
                    "effect": effect_for(target, args),
                    "fingerprint": binding,
                    "attempts": 1,
                    "status": "in_progress",
                }
                persist()
                emit(
                    "tool_started",
                    {
                        "call_id": call_id,
                        "tool": target.name,
                        "arguments": args,
                        "effect": effect_for(target, args),
                    },
                )
                try:
                    value = await pool.call(target, args)
                except Exception as ex:
                    if getattr(ex, "code", None) == "connection_auth":
                        cp["calls"][call_id]["status"] = "not_dispatched"
                        persist()
                        raise
                    raise AiRuntimeError(
                        "Tool transport interrupted",
                        code=(
                            "uncertain_write"
                            if effect_for(target, args) != "read"
                            else "tool_transport"
                        ),
                        source="mcp",
                    ) from ex
                if value.get("isError") and effect_for(target, args) != "read":
                    persist()
                    raise AiRuntimeError(
                        "Write may have partial effects; review required",
                        code="uncertain_write",
                    )
                artifacts = extract_artifacts(target.original_name, call_id, value)
                for artifact in artifacts:
                    artifact.update(
                        payload=artifact.pop("data", {}),
                        saved=effect_for(target, args) != "read",
                        provenance={
                            "tool": target.name,
                            "call_id": call_id,
                            "connection_id": target.connection["id"],
                            "schema_hash": target.schema_hash,
                        },
                    )
                    body = args.get("request", args)
                    artifact["source_request"] = body
                    artifact["payload"].setdefault("source_request", body)
                    form_data = artifact["payload"].get("form_data")
                    if isinstance(form_data, dict) and isinstance(
                        body.get("dataset_id"), int
                    ):
                        form_data.setdefault(
                            "datasource", f"{body['dataset_id']}__table"
                        )
                    validator = state.get("_validate_preview")
                    if (
                        validator
                        and artifact["type"] == "chart"
                        and target.connection.get("is_focal")
                    ):
                        try:
                            artifact["payload"] = validator(artifact["payload"])
                        except AiRuntimeError as ex:
                            if ex.code != "invalid_preview":
                                raise
                            if effect_for(target, args) != "read":
                                cp["calls"][call_id].update(
                                    status="completed", result=value
                                )
                                persist()
                                raise
                            value = {"isError": True, "message": str(ex)}
                            artifacts = []
                            break
                    reference = cp.get("reference_artifact")
                    if reference and artifact["type"] == "chart":
                        artifact["provenance"]["parent_artifact_id"] = reference["id"]
                        artifact["version"] = int(reference.get("version", 1)) + 1
                cp["artifacts"].extend(artifacts)
                cp["calls"][call_id].update(status="completed", result=value)
                cp["tools_used"].append(target.name)
                persist()
                emit(
                    "tool_completed",
                    {
                        "call_id": call_id,
                        "tool": target.name,
                        "result": value,
                        "isError": bool(value.get("isError")),
                    },
                )
                for artifact in artifacts:
                    emit("artifact", artifact)
                visible, truncated = bounded(value, max_chars=10000)
                return json.dumps(
                    {"result": visible, "truncated": truncated, "evidence_ref": call_id}
                )

        sdk_tools: list[SDKTool] = [
            FunctionTool(
                name=t.name,
                description=t.description,
                params_json_schema=t.schema,
                on_invoke_tool=dispatch,
                needs_approval=True,
                strict_json_schema=False,
            )
            for t in tools
        ]

        async def read_evidence(ctx: Any, raw: str) -> str:
            check()
            args = json.loads(raw)
            record = (
                cp["calls"].get(args.get("call_id"))
                or state.get("_read_record", lambda _: None)(args.get("call_id"))
                or {}
            )
            if "result" not in record:
                return json.dumps({"isError": True, "message": "Evidence unavailable"})
            original = next((t for t in tools if t.name == record.get("tool")), None)
            if original is None or fingerprint(
                original, record.get("arguments", {})
            ) != record.get("fingerprint"):
                return json.dumps(
                    {
                        "isError": True,
                        "message": (
                            "Evidence authorization changed; call its source tool again"
                        ),
                    }
                )
            if state.get("_authorize_tool"):
                state["_authorize_tool"](original.original_name)
            body = record.get("arguments", {})
            body = body.get("request", body)
            if isinstance(body.get("dataset_id"), int) and state.get("_authorize_refs"):
                state["_authorize_refs"](
                    [{"type": "dataset", "id": body["dataset_id"]}]
                )
            return json.dumps(read_page(record["result"], args))

        async def read_artifact(ctx: Any, raw: str) -> str:
            check()
            args = json.loads(raw)
            result = state["_read_artifact"](args.get("artifact_id"))
            cp["reference_artifact"] = result
            persist()
            return json.dumps(read_page(result, args, historical=True))

        async def ask_user(ctx: Any, raw: str) -> str:
            return json.dumps({"answer": cp["answers"][ctx.tool_call_id]})

        async def find_tools(ctx: Any, raw: str) -> str:
            check()
            words = json.loads(raw)["query"].lower().replace("_", " ").split()
            ranked = sorted(
                tools,
                key=lambda t: sum(
                    w in (t.original_name + " " + t.description).lower() for w in words
                ),
                reverse=True,
            )
            selected = [
                t
                for t in ranked
                if any(
                    w in (t.original_name + " " + t.description).lower() for w in words
                )
                and (
                    not state.get("_tool_filter")
                    or state["_tool_filter"](t.original_name)
                )
            ]
            return json.dumps(
                {
                    "tools": [
                        {"name": t.name, "description": t.description[:500]}
                        for t in selected
                    ],
                    "note": "All authorized tools are available on every model call",
                }
            )

        for definition, invoke in [
            (READ_EVIDENCE, read_evidence),
            (READ_ARTIFACT, read_artifact),
            (ASK_USER, ask_user),
            (FIND_TOOLS, find_tools),
        ]:
            fn = definition["function"]
            sdk_tools.append(
                FunctionTool(
                    name=fn["name"],
                    description=fn["description"],
                    params_json_schema=fn["parameters"],
                    on_invoke_tool=invoke,
                    needs_approval=True,
                    strict_json_schema=False,
                )
            )
        references = state.get("_artifact_index", lambda: [])()
        instructions = (
            SYSTEM + "\nAll authorized BI tools are available; "
            "find_bi_tools is an optional search aid.\n"
            + state.get("workflow_instructions", "")
        )
        instructions += "\nAuthorized artifact references: " + json.dumps(references)
        instructions += "\nSelected resource references: " + json.dumps(
            state.get("context", [])
        )
        instructions += "\nAdministrator BI guidance: " + str(
            config.get("systemPrompt", "")
        )
        helper_definitions = [READ_EVIDENCE, READ_ARTIFACT, ASK_USER, FIND_TOOLS]

        def select_tools(available: list[Any]) -> list[Any]:
            cp["offered_tools"] = [t.name for t in available]
            return available

        def report_context(usage: dict[str, Any]) -> None:
            cp["context_usage"] = usage
            persist()
            emit("usage", {"usage": usage})

        def report_response_context(response: Any) -> None:
            usage = getattr(response, "usage", None)
            if usage is not None and cp.get("context_usage"):
                report_context(
                    {
                        **cp["context_usage"],
                        "input_tokens": int(usage.input_tokens),
                        "output_tokens": int(usage.output_tokens),
                        "estimated": False,
                    }
                )

        model, client = create_model(
            config,
            budgets,
            transport=state.get("_native_transport"),
            select_tools=select_tools,
            hydrate=state.get("_native_hydrate"),
            on_context=report_context,
        )
        model.before_request = before_request
        settings = ModelSettings(
            max_tokens=int(budgets.get("response_tokens", 4096)),
            extra_body={
                "thinking": {
                    "type": "enabled"
                    if state.get("_native_thinking", True)
                    else "disabled"
                }
            }
            if config.get("llmProvider") == "deepseek"
            else None,
        )

        def definitions() -> list[Any]:
            return [t.definition() for t in tools] + helper_definitions

        from .native_summarization import Summarizer

        summarizer = Summarizer(
            session,
            client,
            config,
            model.allowance,
            check,
            lambda: float(budgets.get("max_active_seconds", 420))
            - prior_active
            - (time.monotonic() - started),
        )
        run_config = RunConfig(
            tracing_disabled=True,
            trace_include_sensitive_data=False,
            call_model_input_filter=context_filter(budgets, definitions, summarizer),
        )
        agent = Agent(
            name="Focal BI",
            instructions=instructions,
            model=model,
            tools=sdk_tools,
            model_settings=settings,
        )
        helper_schemas = {
            d["function"]["name"]: d["function"]["parameters"]
            for d in helper_definitions
        }
        select_tools(sdk_tools)
        catalog = {t.name: t for t in tools}
        run = None
        new_input: Any = state["input_text"]
        if state.get("attachment_ids") and not focused:
            new_input = [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": state["input_text"]}]
                    + [
                        {
                            "type": "input_image",
                            "image_url": f"focal-image:{identifier}",
                        }
                        for identifier in state["attachment_ids"]
                    ],
                }
            ]
        sdk_input: Any = (
            await RunState.from_string(agent, cp["sdk_state"])
            if cp.get("sdk_state")
            else new_input
        )
        generation_id = str(uuid4())
        reasoning_started = False
        reasoning_text = ""
        reasoning_flush = 0.0
        show_reasoning = config.get("showModelReasoning") is True and config.get(
            "llmProvider"
        ) in {"custom", "lmstudio", "deepseek"}

        def publish_reasoning(*, done: bool = False) -> None:
            nonlocal reasoning_flush
            if (
                show_reasoning
                and reasoning_text
                and (done or time.monotonic() - reasoning_flush >= 0.15)
            ):
                emit(
                    "model_reasoning",
                    {
                        "generation_id": generation_id,
                        "message": reasoning_text,
                        "completed": done,
                    },
                )
                reasoning_flush = time.monotonic()

        try:

            async def consume() -> None:
                nonlocal generation_id, reasoning_started, reasoning_text
                assert run is not None
                async for event in run.stream_events():
                    check()
                    if event.type != "raw_response_event":
                        continue
                    data = event.data
                    if data.type == "response.created":
                        generation_id, reasoning_started = str(uuid4()), False
                        reasoning_text = ""
                    elif data.type == "response.output_text.delta":
                        cp["content"] += data.delta
                        emit("message_delta", {"content": data.delta})
                    elif data.type == "response.reasoning_summary_text.delta":
                        reasoning_text = (reasoning_text + data.delta)[:12000]
                        publish_reasoning()
                        if not reasoning_started:
                            emit(
                                "reasoning_status",
                                {"generation_id": generation_id, "message": "Thinking"},
                            )
                            reasoning_started = True
                    elif data.type == "response.completed" and reasoning_started:
                        publish_reasoning(done=True)
                        emit(
                            "reasoning_status",
                            {
                                "generation_id": generation_id,
                                "message": "Thinking",
                                "status": "completed",
                            },
                        )
                    if data.type == "response.completed":
                        report_response_context(data.response)
                        cp["model_rounds"] = cp.get("model_rounds", 0) + 1
                        if cp["model_rounds"] > int(budgets.get("max_rounds", 16)):
                            raise AiRuntimeError(
                                "Model iteration budget reached",
                                code="iteration_budget",
                            )

            # This loop resolves SDK approval checkpoints; Runner owns inference
            # and tool scheduling. Each approved batch is durable before effects.
            while True:
                if isinstance(sdk_input, RunState):
                    poll_inputs()
                    if cp.get("steering"):
                        for interruption in sdk_input.get_interruptions():
                            sdk_input.reject(interruption)
                        request = None
                    else:
                        request = prepare_approvals(
                            sdk_input,
                            state,
                            cp,
                            catalog,
                            helper_schemas,
                            await session.get_items(),
                        )
                    cp["sdk_state"] = sdk_input.to_string()
                    persist()
                    if request:
                        return outcome(
                            "waiting_approval"
                            if request["kind"] == "approval"
                            else "waiting_input",
                            request,
                        )
                run = Runner.run_streamed(
                    agent,
                    input=sdk_input,
                    session=session,
                    max_turns=int(budgets.get("max_rounds", 16)),
                    run_config=run_config,
                )
                task = asyncio.create_task(consume())
                try:
                    while not task.done():
                        check()
                        if prior_active + time.monotonic() - started > float(
                            budgets.get("max_active_seconds", 420)
                        ):
                            raise AiRuntimeError(
                                "Turn time budget reached", code="time_budget"
                            )
                        await asyncio.wait({task}, timeout=0.2)
                    await task
                    cp["usage"] = {
                        key: int(cp.get("usage_base", {}).get(key, 0))
                        + int(getattr(run.context_wrapper.usage, key))
                        for key in ("input_tokens", "output_tokens")
                    }
                finally:
                    if not task.done():
                        run.cancel()
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                if not run.interruptions:
                    break
                sdk_input = run.to_state()
                cp["sdk_state"] = sdk_input.to_string()
                persist()
        except AgentsException as ex:
            cause = ex.__cause__
            if isinstance(cause, AiRuntimeError):
                raise cause from None
            raise AiRuntimeError(
                "Agent execution interrupted", code="sdk_execution"
            ) from None
        except AiRuntimeError as ex:
            if ex.code == "accepted_steering":
                cp["resume_focus"] = "\n".join(cp.pop("steering"))
                cp.pop("sdk_state", None)
                return outcome("queued")
            if ex.code == "context_budget":
                return outcome(
                    "waiting_input",
                    {
                        "kind": "clarification",
                        "reason": "context",
                        "message": (
                            "The required input is too large for this model. "
                            "Enter a shorter, focused request to continue "
                            "using saved evidence, or cancel and choose "
                            "a larger model in a new branch."
                        ),
                    },
                )
            raise
        except APIError as ex:
            raise AiRuntimeError(
                "LLM request failed", code="provider_http", source="llm"
            ) from ex
        finally:
            if run is not None and not run.is_complete:
                run.cancel()
            await client.close()
        cp["session_end"] = len(await session.get_items())
        cp.pop("sdk_state", None)
        return outcome("completed")

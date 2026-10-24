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
"""Streaming Chat Completions and Responses adapters using separate LLM credentials.

Responses continuation follows the official OpenAI function-calling protocol:
https://developers.openai.com/api/docs/guides/function-calling
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import uuid4

from superset.utils import json

from .context import digest
from .contracts import AiRuntimeError, Generation, TurnCancelledError


async def cancellable(awaitable: Any, cancelled: Callable[[], bool]) -> Any:
    """Cancel an active upstream await promptly when the user cancels the turn."""
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            if cancelled():
                raise TurnCancelledError("Turn cancelled", code="cancelled")
            await asyncio.wait({task}, timeout=0.2)
        return await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def sse_events(response: Any) -> AsyncIterator[dict[str, Any]]:
    """Parse multiline SSE data and tolerate keepalive comments."""
    chunks: list[str] = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            chunks.append(line[5:].lstrip())
        elif not line and chunks:
            data, chunks = "\n".join(chunks), []
            if data == "[DONE]":
                return
            yield json.loads(data)
    if chunks and "\n".join(chunks) != "[DONE]":
        yield json.loads("\n".join(chunks))


def response_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate canonical messages to Responses input items without dropping calls."""
    items = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": message["content"],
                }
            )
            continue
        if message.get("content"):
            content = message["content"]
            if isinstance(content, list):
                content = [
                    {"type": "input_text", "text": p["text"]}
                    if p.get("type") == "text"
                    else {"type": "input_image", "image_url": p["image_url"]["url"]}
                    for p in content
                ]
            items.append({"role": role, "content": content})
        for call in message.get("tool_calls", []):
            items.append(
                {"type": "function_call", "call_id": call["id"], **call["function"]}
            )
    return items


class HTTPProvider:
    """One model generation per request, with no replay after streamed tokens."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def generate(  # noqa: C901 - streaming, batching and bounded retry lifecycle
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        emit: Callable[[str, dict[str, Any]], None],
        cancelled: Callable[[], bool],
        continuation: dict[str, Any],
    ) -> Generation:
        """Retry transient failures twice only before any visible text is emitted."""
        visible = False
        reasoning_started = False
        pending: dict[str, dict[str, Any]] = {}
        generation_id = str(uuid4())

        def flush() -> None:
            for payload in list(pending.values()):
                kind = str(payload.get("activity_kind", "reasoning_summary"))
                emit(
                    kind,
                    {
                        key: value
                        for key, value in payload.items()
                        if key != "activity_kind"
                    },
                )
            pending.clear()

        def tracked(kind: str, payload: dict[str, Any]) -> None:
            nonlocal visible, reasoning_started
            if kind in {"message_delta", "reasoning_summary", "model_reasoning"}:
                visible = True
            if kind == "model_timing":
                payload = {**payload, "generation_id": generation_id}
            if kind in {"reasoning_status", "reasoning_summary", "model_reasoning"}:
                if payload.get("only_existing") and not reasoning_started:
                    return
                reasoning_started = True
                payload = {**payload, "generation_id": generation_id}
            if kind in {"reasoning_summary", "model_reasoning"} and not payload.get(
                "completed"
            ):
                pending[f"{kind}:{payload.get('summary_id', 'reasoning')}"] = {
                    **payload,
                    "activity_kind": kind,
                }
                return
            flush()
            emit(kind, payload)

        async def flush_periodically() -> None:
            while True:
                await asyncio.sleep(0.15)
                flush()

        flusher = asyncio.create_task(flush_periodically())
        try:
            for attempt in range(3):
                try:
                    return await self._generate_once(
                        messages,
                        tools,
                        emit=tracked,
                        cancelled=cancelled,
                        continuation=continuation,
                    )
                except AiRuntimeError as ex:
                    if visible or attempt == 2 or not getattr(ex, "retryable", False):
                        raise
                    tracked(
                        "reasoning_status",
                        {
                            "message": "Thinking",
                            "status": "interrupted",
                            "only_existing": True,
                        },
                    )
                    generation_id = str(uuid4())
                    reasoning_started = False
                    await cancellable(asyncio.sleep(0.5 * (2**attempt)), cancelled)
            raise AssertionError("Unreachable model retry state")
        except BaseException as ex:
            flush()
            tracked(
                "reasoning_status",
                {
                    "message": "Thinking",
                    "status": "cancelled"
                    if isinstance(ex, TurnCancelledError)
                    else "interrupted",
                    "only_existing": True,
                },
            )
            raise
        finally:
            flusher.cancel()
            try:
                await flusher
            except asyncio.CancelledError:
                pass
            flush()

    async def _generate_once(  # noqa: C901 - execution state machine
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        emit: Callable[[str, dict[str, Any]], None],
        cancelled: Callable[[], bool],
        continuation: dict[str, Any],
    ) -> Generation:  # noqa: C901 - explicit execution state machine
        """Stream directly while collecting fragmented function calls for one turn."""
        import httpx  # pylint: disable=import-outside-toplevel

        config = self.config
        started = time.monotonic()
        first_output_at: float | None = None
        first_answer_at: float | None = None
        outcome = "interrupted"
        canonical_messages = messages
        input_hash = digest(canonical_messages)
        if any(isinstance(m.get("content"), list) for m in messages):
            from superset.ai_runtime.images import hydrate

            messages = hydrate(messages, config)
        responses = config.get("adapter", config.get("llmAdapter")) in {
            "responses",
            "openai_responses",
        }
        base = str(config.get("llmApiBaseUrl", config.get("base_url", ""))).rstrip("/")
        if not base:
            raise AiRuntimeError(
                "LLM endpoint is not configured",
                code="provider_configuration",
                source="llm",
            )
        body: dict[str, Any] = {
            "model": config.get("llmModel", config.get("model")),
            "stream": True,
        }
        if responses:
            if tools:
                body["tools"] = [
                    {"type": "function", **tool["function"]} for tool in tools
                ]
            body["instructions"] = "\n".join(
                str(message["content"])
                for message in messages
                if message["role"] == "system"
            )
            non_system = [
                message for message in messages if message["role"] != "system"
            ]
            prior = continuation.get("provider_response_id")
            offset = int(continuation.get("message_count", 0))
            prefix_count = int(continuation.get("input_count", -1))
            prefix_matches = 0 <= prefix_count <= len(
                canonical_messages
            ) and continuation.get("input_hash") == digest(
                canonical_messages[:prefix_count]
            )
            if prior and prefix_matches and 0 <= offset <= len(messages):
                body["previous_response_id"] = prior
                body["input"] = response_input(
                    [
                        message
                        for message in messages[offset:]
                        if message["role"] != "system"
                    ]
                )
            else:
                body["input"] = response_input(non_system)
        else:
            body.update(messages=messages, stream_options={"include_usage": True})
            # Compatible servers can reject an empty tool array during validation.
            if tools:
                body["tools"] = tools
        key = config.get("llmApiKey", config.get("api_key", ""))
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        result = Generation()
        calls: dict[int, dict[str, Any]] = {}
        completed = False
        reasoning_seen = False
        reasoning_chars = 0
        show_reasoning = config.get("showModelReasoning") is True and config.get(
            "llmProvider"
        ) in {"custom", "lmstudio"}
        summaries: dict[tuple[str, int], str] = {}
        reasoning_ids: dict[int, str] = {}
        finished_summaries: set[tuple[str, int]] = set()

        def summary_update(item_id: str, index: int, text: str, *, done: bool) -> None:
            nonlocal reasoning_seen
            if not reasoning_seen:
                reasoning_seen = True
                emit("reasoning_status", {"message": "Thinking"})
            summaries[(item_id, index)] = text
            if done:
                finished_summaries.add((item_id, index))
            emit(
                "reasoning_summary",
                {
                    "summary_id": f"{item_id}:{index}",
                    "message": text,
                    "completed": done,
                },
            )

        endpoint = "/responses" if responses else "/chat/completions"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=15),
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST", base + endpoint, json=body, headers=headers
                ) as response:
                    if response.status_code >= 300:
                        error = AiRuntimeError(
                            f"LLM request failed (HTTP {response.status_code})",
                            code="provider_http",
                            source="llm",
                        )
                        error.retryable = (
                            response.status_code == 429 or response.status_code >= 500
                        )
                        raise error
                    iterator = sse_events(response).__aiter__()
                    while True:
                        try:
                            event = await cancellable(iterator.__anext__(), cancelled)
                        except StopAsyncIteration:
                            break
                        if event.get("error") or event.get("type") in {
                            "error",
                            "response.failed",
                            "response.incomplete",
                        }:
                            raise AiRuntimeError(
                                "LLM generation failed",
                                code="provider_generation",
                                source="llm",
                            )
                        if first_output_at is None and (
                            event.get("type")
                            in {
                                "response.output_text.delta",
                                "response.reasoning_summary_text.delta",
                                "response.function_call_arguments.delta",
                            }
                            or any(
                                (choice.get("delta") or {}).get(field)
                                for choice in (event.get("choices") or [])
                                for field in (
                                    "content",
                                    "reasoning_content",
                                    "tool_calls",
                                )
                            )
                        ):
                            first_output_at = time.monotonic()
                        if first_answer_at is None and (
                            event.get("type") == "response.output_text.delta"
                            or any(
                                (choice.get("delta") or {}).get("content")
                                for choice in (event.get("choices") or [])
                            )
                        ):
                            first_answer_at = time.monotonic()
                        if responses:
                            event_type = event.get("type")
                            if event_type == "response.output_text.delta":
                                delta = event.get("delta", "")
                                result.content += delta
                                emit("message_delta", {"content": delta})
                            elif event_type in {
                                "response.reasoning_summary_text.delta",
                                "response.reasoning_summary_text.done",
                            }:
                                item_id = str(
                                    event.get("item_id", event.get("output_index", 0))
                                )
                                index = int(event.get("summary_index", 0))
                                done = event_type.endswith(".done")
                                text = (
                                    str(event.get("text", ""))
                                    if done
                                    else (
                                        summaries.get((item_id, index), "")
                                        + str(event.get("delta", ""))
                                    )
                                )
                                summary_update(item_id, index, text, done=done)
                            elif event_type == "response.output_item.added":
                                item = event["item"]
                                reasoning_ids[int(event.get("output_index", 0))] = str(
                                    item.get("id", event.get("output_index", 0))
                                )
                                if (
                                    item.get("type") == "reasoning"
                                    and not reasoning_seen
                                ):
                                    reasoning_seen = True
                                    emit("reasoning_status", {"message": "Thinking"})
                                if item.get("type") == "function_call":
                                    calls[event["output_index"]] = {
                                        "id": item["call_id"],
                                        "type": "function",
                                        "function": {
                                            "name": item["name"],
                                            "arguments": item.get("arguments", ""),
                                        },
                                    }
                            elif event_type == "response.function_call_arguments.delta":
                                call = calls.get(event["output_index"])
                                if call:
                                    call["function"]["arguments"] += event["delta"]
                            elif event_type == "response.function_call_arguments.done":
                                call = calls.get(event["output_index"])
                                if call:
                                    call["function"]["arguments"] = event["arguments"]
                            elif event_type == "response.completed":
                                data = event["response"]
                                for output_index, item in enumerate(
                                    data.get("output", [])
                                ):
                                    if item.get("type") == "reasoning":
                                        item_id = str(
                                            item.get(
                                                "id",
                                                reasoning_ids.get(
                                                    output_index, str(output_index)
                                                ),
                                            )
                                        )
                                        for index, part in enumerate(
                                            item.get("summary", [])
                                        ):
                                            if part.get(
                                                "type"
                                            ) == "summary_text" and isinstance(
                                                part.get("text"), str
                                            ):
                                                summary_update(
                                                    item_id,
                                                    index,
                                                    part["text"],
                                                    done=True,
                                                )
                                for (item_id, index), text in list(summaries.items()):
                                    if (item_id, index) not in finished_summaries:
                                        summary_update(item_id, index, text, done=True)
                                result.usage = data.get("usage") or {}
                                result.continuation = {
                                    "provider_response_id": data["id"],
                                    "response_items": data.get("output", []),
                                    "message_count": len(messages) + 1,
                                    "input_count": len(canonical_messages),
                                    "input_hash": input_hash,
                                }
                                completed = True
                        else:
                            if event.get("usage"):
                                result.usage = event["usage"]
                            for choice in event.get("choices") or []:
                                if choice.get("index", 0) != 0:
                                    continue
                                finish = choice.get("finish_reason")
                                if finish in {"length", "content_filter"}:
                                    raise AiRuntimeError(
                                        "LLM generation was incomplete",
                                        code="provider_incomplete",
                                        source="llm",
                                    )
                                if finish:
                                    completed = True
                                delta = choice.get("delta") or {}
                                # Compatible servers use either spelling; normalize
                                # continuation data through the same privacy gate.
                                thought = delta.get("reasoning_content") or delta.get(
                                    "reasoning"
                                )
                                if isinstance(thought, str) and thought:
                                    if not reasoning_seen:
                                        reasoning_seen = True
                                        emit(
                                            "reasoning_status", {"message": "Thinking"}
                                        )
                                    reasoning_chars += len(thought)
                                    result.provider_fields["reasoning_content"] = (
                                        result.provider_fields.get(
                                            "reasoning_content", ""
                                        )
                                        + thought
                                    )
                                    if show_reasoning:
                                        emit(
                                            "model_reasoning",
                                            {
                                                "message": result.provider_fields[
                                                    "reasoning_content"
                                                ],
                                                "completed": False,
                                            },
                                        )
                                if delta.get("content"):
                                    result.content += delta["content"]
                                    emit("message_delta", {"content": delta["content"]})
                                for fragment in delta.get("tool_calls") or []:
                                    call = calls.setdefault(
                                        fragment["index"],
                                        {
                                            "id": "",
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        },
                                    )
                                    if fragment.get("id"):
                                        call["id"] += fragment["id"]
                                    for key in ("name", "arguments"):
                                        piece = (fragment.get("function") or {}).get(
                                            key
                                        )
                                        if piece is not None:
                                            if not isinstance(piece, str):
                                                raise AiRuntimeError(
                                                    "Invalid streamed tool field",
                                                    code="provider_protocol",
                                                    source="llm",
                                                )
                                            call["function"][key] += piece
            if reasoning_seen:
                if show_reasoning and result.provider_fields.get("reasoning_content"):
                    emit(
                        "model_reasoning",
                        {
                            "message": result.provider_fields["reasoning_content"],
                            "completed": completed,
                        },
                    )
                emit(
                    "reasoning_status", {"message": "Thinking", "completed": completed}
                )
            if not completed:
                raise AiRuntimeError(
                    "LLM stream ended before completion",
                    code="provider_incomplete",
                    source="llm",
                )
            outcome = "completed"
        except (AiRuntimeError, TurnCancelledError):
            raise
        except (TypeError, KeyError, ValueError) as ex:
            raise AiRuntimeError(
                "The model returned invalid streamed data",
                code="provider_protocol",
                source="llm",
            ) from ex
        except Exception as ex:
            error = AiRuntimeError(
                "LLM transport failed", code="provider_transport", source="llm"
            )
            error.retryable = isinstance(
                ex, (httpx.TimeoutException, httpx.NetworkError)
            )
            raise error from ex
        finally:
            emit(
                "model_timing",
                {
                    "status": outcome,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "time_to_first_output_ms": round((first_output_at - started) * 1000)
                    if first_output_at
                    else None,
                    "time_to_first_answer_ms": round((first_answer_at - started) * 1000)
                    if first_answer_at
                    else None,
                    "reasoning_characters": reasoning_chars,
                    "answer_characters": len(result.content),
                    "usage": result.usage,
                },
            )
        result.calls = [calls[index] for index in sorted(calls)]
        if any(not call["id"] or not call["function"]["name"] for call in result.calls):
            raise AiRuntimeError(
                "Incomplete streamed tool call", code="provider_protocol", source="llm"
            )
        return result

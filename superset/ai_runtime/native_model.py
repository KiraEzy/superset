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
"""Public SDK model adapter with a final wire-budget/provider-field boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from typing import Any

import httpx
from agents import OpenAIChatCompletionsModel
from openai import APIConnectionError, AsyncOpenAI, BadRequestError

from superset.utils import json

from .contracts import AiRuntimeError
from .native_context import fit_input, request_cost

_input: ContextVar[list[Any] | None] = ContextVar("focal_sdk_input", default=None)


def assistant_reasoning(items: list[Any]) -> list[str]:
    """Align reasoning and assistant generations using public SDK items."""
    result: list[str] = []
    pending = ""
    active = False
    for item in items:
        kind = item.get("type")
        if kind == "reasoning":
            if active:
                result.append(pending)
                active = False
            pending = "\n".join(p.get("text", "") for p in item.get("summary", []))
        elif kind in {"function_call", "message"} and (
            kind == "function_call" or item.get("role") == "assistant"
        ):
            active = True
        elif item.get("role") == "assistant":
            active = True
        else:
            if active:
                result.append(pending)
            active, pending = False, ""
    if active:
        result.append(pending)
    return result


class NativeChatModel(OpenAIChatCompletionsModel):
    """Consume Runner input directly; the SDK owns conversion and stream assembly."""

    allowance: int = 24576
    select_tools: Callable[[list[Any]], list[Any]] | None = None
    before_request: Callable[[], None] | None = None

    async def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:  # noqa: C901
        if self.before_request:
            self.before_request()
        source = kwargs.get("input", args[1] if len(args) > 1 else [])
        instructions = kwargs.get("system_instructions", args[0] if args else None)
        tools = kwargs.get("tools", args[3] if len(args) > 3 else [])
        if self.select_tools:
            tools = self.select_tools(tools)
        definitions = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.params_json_schema,
            }
            for t in tools
        ]
        items = (
            source
            if isinstance(source, list)
            else [{"role": "user", "content": source}]
        )
        items = [
            i
            for i in items
            if i.get("type") != "reasoning"
            or i.get("provider_data", {}).get("model", self.model) == self.model
        ]
        visible = False
        for attempt in range(2):
            prepared, guidance = fit_input(
                items,
                instructions,
                definitions,
                int(self.allowance * (0.8 if attempt else 0.95)),
            )
            positional = list(args)
            values = dict(kwargs)
            for name, index, value in [
                ("system_instructions", 0, guidance),
                ("input", 1, prepared),
                ("tools", 3, tools),
            ]:
                if index < len(positional):
                    positional[index] = value
                else:
                    values[name] = value
            token = _input.set(prepared)
            try:
                async for event in super().stream_response(*positional, **values):
                    if event.type.endswith(".delta"):
                        visible = True
                    yield event
                return
            except (APIConnectionError, AiRuntimeError, BadRequestError) as ex:
                error = (
                    ex.__cause__
                    if isinstance(ex, APIConnectionError)
                    and isinstance(ex.__cause__, AiRuntimeError)
                    else ex
                )
                context_error = getattr(error, "code", None) == "context_budget" or (
                    isinstance(error, BadRequestError)
                    and (
                        getattr(error, "code", None)
                        in {"context_length_exceeded", "max_context_length_exceeded"}
                        or any(
                            text in str(error).lower()
                            for text in [
                                "maximum context length",
                                "context window exceeded",
                                "too many tokens",
                            ]
                        )
                    )
                )
                if context_error and not visible and attempt == 0:
                    continue
                if context_error:
                    raise AiRuntimeError(
                        "The required input cannot fit this model",
                        code="context_budget",
                    ) from None
                raise error from None
            finally:
                _input.reset(token)


def hydrate_body_images(
    body: dict[str, Any],
    config: dict[str, Any],
    hydrate: Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]
    | None,
) -> None:
    """Resolve scoped private image IDs only at the transport boundary."""
    for message in body.get("messages", []):
        parts = message.get("content")
        if not isinstance(parts, list):
            continue
        for index, part in enumerate(parts):
            if part.get("type") != "image_url":
                continue
            url = part["image_url"]["url"]
            if not config.get("vision") or not url.startswith("focal-image:"):
                raise AiRuntimeError(
                    "Choose an image-verified model and an authorized attachment",
                    code="image_scope",
                )
            if hydrate is None:
                from .images import hydrate as default_hydrate

                hydrate = default_hydrate
            try:
                parts[index] = hydrate(
                    [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_ref",
                                    "image_id": url.removeprefix("focal-image:"),
                                }
                            ],
                        }
                    ],
                    config,
                )[0]["content"][0]
            except (ValueError, LookupError) as ex:
                raise AiRuntimeError(
                    "Private image is unavailable", code="image_scope"
                ) from ex


def create_model(
    config: dict[str, Any],
    budgets: dict[str, Any],
    *,
    transport: Any = None,
    select_tools: Callable[[list[Any]], list[Any]] | None = None,
    hydrate: Callable[[list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]
    | None = None,
    on_context: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[NativeChatModel, AsyncOpenAI]:
    """Build a scoped client; no environment credentials or provider fallback."""
    if config.get("adapter", "chat_completions") != "chat_completions":
        raise AiRuntimeError(
            "This Chat runtime requires a verified Chat Completions connection",
            code="unsupported_adapter",
        )
    allowance = (
        int(budgets.get("context_window_tokens", 32768))
        - int(budgets.get("response_tokens", 4096))
        - int(budgets.get("tool_result_tokens", 4096))
    )

    def wire_guard(request: httpx.Request) -> httpx.Request:
        body = json.loads(request.content)
        # The pinned converter restores reasoning for tool-call messages, but
        # drops it for final assistant messages. DeepSeek's tool-bearing replay
        # requires both. Restore from the actual SDK input, never another history.
        if config.get("llmProvider") == "deepseek" and body.get("tools"):
            reasons = assistant_reasoning(_input.get() or [])
            assistants = [m for m in body["messages"] if m["role"] == "assistant"]
            if len(reasons) != len(assistants):
                raise AiRuntimeError(
                    "Provider history conversion differs", code="provider_fields"
                )
            for message, reasoning in zip(assistants, reasons, strict=True):
                message["reasoning_content"] = reasoning
        # Include all serialized schemas/settings/images, not just visible text.
        estimated_input = request_cost(body)
        if estimated_input > allowance:
            raise AiRuntimeError(
                "This input cannot fit this model; "
                "reduce attachments or select a larger model",
                code="context_budget",
            )
        (on_context or (lambda usage: None))(
            {
                "model": config["llmModel"],
                "model_id": config.get("model_id"),
                "context_window_tokens": int(
                    budgets.get("context_window_tokens", 32768)
                ),
                "input_tokens": estimated_input,
                "output_tokens": 0,
                "output_limit_tokens": int(budgets.get("response_tokens", 4096)),
                "input_allowance_tokens": allowance,
                "tool_result_reserve_tokens": int(
                    budgets.get("tool_result_tokens", 4096)
                ),
                "estimated": True,
            }
        )
        hydrate_body_images(body, config, hydrate)
        headers = dict(request.headers)
        headers.pop("content-length", None)
        return httpx.Request(
            request.method,
            request.url,
            headers=headers,
            content=json.dumps(body).encode(),
            extensions=request.extensions,
        )

    class ProviderTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.inner = transport or httpx.AsyncHTTPTransport(retries=0)

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            await request.aread()
            return await self.inner.handle_async_request(wire_guard(request))

        async def aclose(self) -> None:
            await self.inner.aclose()

    client = AsyncOpenAI(
        api_key=config.get("llmApiKey") or "not-required",
        base_url=config["llmApiBaseUrl"].rstrip("/"),
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=ProviderTransport(),
            timeout=httpx.Timeout(120, connect=15),
            follow_redirects=False,
            trust_env=False,
        ),
    )
    model = NativeChatModel(config["llmModel"], client)
    model.allowance, model.select_tools = allowance, select_tools
    return model, client


def context_filter(
    budgets: dict[str, Any], definitions: Any, summarizer: Any = None
) -> Any:
    """Trim old complete user exchanges in the disposable SDK model view."""
    from agents.run import ModelInputData

    allowance = (
        int(budgets.get("context_window_tokens", 32768))
        - int(budgets.get("response_tokens", 4096))
        - int(budgets.get("tool_result_tokens", 4096))
    )

    async def prepare(data: Any) -> Any:
        source = list(data.model_data.input)
        tools = definitions() if callable(definitions) else definitions
        if summarizer is not None:
            source = await summarizer.prepare(
                source, data.model_data.instructions, tools
            )
        items, instructions = fit_input(
            source,
            data.model_data.instructions,
            tools,
            allowance,
        )
        return ModelInputData(input=items, instructions=instructions)

    return prepare

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

from __future__ import annotations



import json

import logging

import os

import uuid

from typing import Any, Iterator

from urllib.parse import urlparse, urlunparse



import requests

from flask import current_app



logger = logging.getLogger(__name__)


class AiStreamError(ValueError):
    """Structured error for AI chat SSE events."""

    def __init__(
        self,
        message: str,
        *,
        source: str = "agent",
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.code = code

    def to_event(self) -> dict[str, Any]:
        event: dict[str, Any] = {
            "type": "error",
            "message": str(self),
            "source": self.source,
        }
        if self.code:
            event["code"] = self.code
        return event


MCP_ACCEPT = "application/json, text/event-stream"

REQUEST_TIMEOUT = 1200

MAX_TOOL_ITERATIONS = 120

LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "0.0.0.0"})  # noqa: S104

MAX_TOOL_RESULT_CHARS = 48_000

SYNTHETIC_MCP_TOOLS = frozenset({"search_tools", "call_tool"})



AGENT_SYSTEM_PROMPT = """You are an AI assistant embedded in Apache Superset with MCP tools \

for databases, datasets, SQL, charts, and dashboards.



Rules:

- Use tools to answer data questions. Do not invent database contents.

- Typical flow: list_databases → list_datasets or execute_sql → generate_chart.

- Many Superset MCP tools expect a top-level "request" wrapper, for example:

  list_databases(request={"page": 1})

  execute_sql(request={"database_id": 2, "sql": "SELECT ...", "limit": 100})

  generate_chart(request={"dataset_id": 5, "config": {...}, "save_chart": true})

- For pie charts use generate_chart with config chart_type "pie", plus dimension and metric.

- Use real column names from get_dataset_info before charting.

- Share explore/preview URLs returned by chart tools.

- When creating charts for the user, use save_chart: true so charts persist and appear inline in chat.

- Be concise in your final reply to the user."""


def _resolve_agent_max_iterations(agent_max_iterations: int | None) -> int:
    if isinstance(agent_max_iterations, int) and agent_max_iterations > 0:
        return agent_max_iterations
    config_val = current_app.config.get("AI_AGENT_MAX_ITERATIONS")
    if isinstance(config_val, int) and config_val > 0:
        return config_val
    return MAX_TOOL_ITERATIONS


def _resolve_agent_system_prompt(system_prompt: str | None) -> str:
    if isinstance(system_prompt, str) and system_prompt.strip():
        return system_prompt.strip()
    config_prompt = current_app.config.get("AI_AGENT_SYSTEM_PROMPT")
    if isinstance(config_prompt, str) and config_prompt.strip():
        return config_prompt.strip()
    return AGENT_SYSTEM_PROMPT


def _get_request_base_url() -> str | None:
    try:
        from flask import has_request_context, request

        if not has_request_context():
            return None
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host") or request.host
        if host:
            return f"{scheme}://{host}".rstrip("/")
    except Exception:  # noqa: BLE001
        return None
    return None


def rewrite_superset_url_for_client(url: str) -> str:
    """Rewrite localhost or relative Superset URLs to the client's request origin."""
    if not url or not url.strip():
        return url
    trimmed = url.strip()
    base = _get_request_base_url()
    if not base:
        return trimmed
    base_parsed = urlparse(base)
    if trimmed.startswith("/"):
        return f"{base.rstrip('/')}{trimmed}"
    parsed = urlparse(trimmed)
    if parsed.scheme in ("http", "https") and parsed.hostname in LOCAL_HOSTNAMES:
        return urlunparse(
            (
                base_parsed.scheme,
                base_parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    return trimmed


def _running_in_docker() -> bool:

    return os.path.exists("/.dockerenv")





def _docker_host() -> str:

    return current_app.config.get("AI_DOCKER_HOST", "host.docker.internal")





def normalize_url_for_backend(url: str, *, service_host: str | None = None) -> str:

    """Rewrite localhost URLs so the Superset backend can reach host services."""

    if not url:

        return url



    parsed = urlparse(url.strip())

    hostname = parsed.hostname or ""



    if _running_in_docker():

        if hostname in {"localhost", "127.0.0.1"}:

            if service_host:

                netloc = f"{service_host}:{parsed.port}" if parsed.port else service_host

            else:

                docker_host = _docker_host()

                port_suffix = f":{parsed.port}" if parsed.port else ""

                netloc = f"{docker_host}{port_suffix}"

            parsed = parsed._replace(netloc=netloc)

            return urlunparse(parsed)



    return url.strip()





def normalize_mcp_url(url: str) -> str:

    internal = current_app.config.get("AI_MCP_INTERNAL_URL")

    if internal:

        return internal

    return normalize_url_for_backend(url, service_host="superset_mcp")





def normalize_llm_base_url(url: str) -> str:

    override = current_app.config.get("AI_LLM_INTERNAL_BASE_URL")

    if override:

        return override.rstrip("/")

    return normalize_url_for_backend(url.rstrip("/"))





def _auth_headers(api_key: str | None) -> dict[str, str]:

    headers: dict[str, str] = {}

    if api_key and api_key.strip():

        headers["Authorization"] = f"Bearer {api_key.strip()}"

    return headers





def _parse_sse_json(text: str) -> dict[str, Any] | None:

    for line in reversed(text.splitlines()):

        if line.startswith("data: "):

            try:

                return json.loads(line[6:])

            except Exception:  # noqa: S110

                continue

    return None





def mcp_jsonrpc(

    mcp_url: str,

    method: str,

    params: dict[str, Any] | None = None,

    *,

    bearer_token: str | None = None,

    request_id: int = 1,

) -> dict[str, Any]:

    url = normalize_mcp_url(mcp_url)

    headers = {

        "Content-Type": "application/json",

        "Accept": MCP_ACCEPT,

        **_auth_headers(bearer_token),

    }

    payload = {

        "jsonrpc": "2.0",

        "method": method,

        "params": params or {},

        "id": request_id,

    }



    response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)

    response.raise_for_status()



    content_type = response.headers.get("Content-Type", "")

    if "text/event-stream" in content_type:

        parsed = _parse_sse_json(response.text)

        if parsed is None:

            raise ValueError("Unable to parse MCP SSE response")

        return parsed



    return response.json()





def mcp_list_tools(

    mcp_url: str,

    *,

    bearer_token: str | None = None,

) -> list[dict[str, Any]]:

    result = mcp_jsonrpc(mcp_url, "tools/list", bearer_token=bearer_token)

    if "error" in result:

        raise ValueError(result["error"].get("message", "MCP tools/list failed"))

    tools = result.get("result", {}).get("tools", [])

    if not isinstance(tools, list):

        return []

    return [tool for tool in tools if isinstance(tool, dict)]





def mcp_call_tool(

    mcp_url: str,

    tool_name: str,

    arguments: dict[str, Any] | None = None,

    *,

    bearer_token: str | None = None,

) -> Any:

    tool_args = arguments or {}

    result = mcp_jsonrpc(

        mcp_url,

        "tools/call",

        {

            "name": tool_name,

            "arguments": tool_args,

        },

        bearer_token=bearer_token,

    )

    if "error" in result:

        raise ValueError(result["error"].get("message", "MCP tool call failed"))

    return result.get("result")





def _simplify_json_schema(schema: Any) -> dict[str, Any]:

    """Strip unsupported JSON Schema features for OpenAI-compatible tool calling."""

    if not isinstance(schema, dict):

        return {"type": "object", "properties": {}}



    simplified: dict[str, Any] = {

        "type": schema.get("type", "object"),

        "properties": schema.get("properties", {}),

    }

    if required := schema.get("required"):

        simplified["required"] = required

    if description := schema.get("description"):

        simplified["description"] = description

    return simplified





def mcp_tools_to_openai(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:

    openai_tools: list[dict[str, Any]] = []

    for tool in mcp_tools:

        name = tool.get("name")

        if not name or not isinstance(name, str):

            continue

        schema = tool.get("inputSchema") or {"type": "object", "properties": {}}

        description = tool.get("description") or name

        openai_tools.append(

            {

                "type": "function",

                "function": {

                    "name": name,

                    "description": str(description)[:4000],

                    "parameters": _simplify_json_schema(schema),

                },

            }

        )

    return openai_tools





def _uses_tool_search_proxy(mcp_tools: list[dict[str, Any]]) -> bool:

    names = {tool.get("name") for tool in mcp_tools}

    return "call_tool" in names and len(names) <= 6





def _parse_mcp_structured_content(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip().startswith("{"):
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        continue
    if isinstance(result.get("success"), bool) or result.get("form_data"):
        return result
    return None


def _extract_chart_payload(tool_name: str, raw_result: Any) -> dict[str, Any] | None:
    if tool_name != "generate_chart":
        return None
    structured = _parse_mcp_structured_content(raw_result)
    if not structured or not structured.get("success"):
        return None
    form_data = structured.get("form_data")
    if not isinstance(form_data, dict) or not form_data:
        return None
    chart_info = structured.get("chart") if isinstance(structured.get("chart"), dict) else {}
    slice_id = chart_info.get("id")
    title = chart_info.get("slice_name") or chart_info.get("title")
    viz_type = (
        chart_info.get("viz_type")
        or form_data.get("viz_type")
        or structured.get("viz_type")
    )
    if not isinstance(viz_type, str) or not viz_type.strip():
        return None
    payload: dict[str, Any] = {
        "title": title if isinstance(title, str) else None,
        "viz_type": viz_type.strip(),
        "form_data": form_data,
    }
    if isinstance(slice_id, int):
        payload["slice_id"] = slice_id
    explore_url = structured.get("explore_url")
    if isinstance(explore_url, str) and explore_url.strip():
        payload["explore_url"] = rewrite_superset_url_for_client(explore_url.strip())
    form_data_key = structured.get("form_data_key")
    if isinstance(form_data_key, str) and form_data_key.strip():
        payload["form_data_key"] = form_data_key.strip()
    return payload


def _serialize_tool_result(result: Any) -> str:

    if result is None:

        return "null"

    if isinstance(result, dict):

        content = result.get("content")

        if isinstance(content, list):

            parts: list[str] = []

            for block in content:

                if isinstance(block, dict) and block.get("type") == "text":

                    parts.append(str(block.get("text", "")))

                elif isinstance(block, dict):

                    parts.append(json.dumps(block, default=str))

            if parts:

                text = "\n".join(parts)

                return text[:MAX_TOOL_RESULT_CHARS]

        if "structuredContent" in result:

            text = json.dumps(result["structuredContent"], default=str)

            return text[:MAX_TOOL_RESULT_CHARS]

    text = json.dumps(result, default=str)

    return text[:MAX_TOOL_RESULT_CHARS]





def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:

    if isinstance(raw_arguments, dict):

        return raw_arguments

    if isinstance(raw_arguments, str) and raw_arguments.strip():

        return json.loads(raw_arguments)

    return {}





def _resolve_mcp_tool_invocation(

    tool_name: str,

    arguments: dict[str, Any],

    *,

    uses_proxy: bool,

) -> tuple[str, dict[str, Any]]:

    if uses_proxy and tool_name != "call_tool":

        return "call_tool", {"name": tool_name, "arguments": arguments}

    return tool_name, arguments





def _extract_text_content(content: Any) -> str:

    if isinstance(content, str):

        return content

    if isinstance(content, list):

        parts: list[str] = []

        for block in content:

            if isinstance(block, dict) and block.get("type") == "text":

                parts.append(str(block.get("text", "")))

        return "\n".join(parts)

    if content is None:

        return ""

    return str(content)





def _llm_chat_completion(

    *,

    base_url: str,

    headers: dict[str, str],

    model: str,

    messages: list[dict[str, Any]],

    tools: list[dict[str, Any]] | None = None,

) -> dict[str, Any]:

    payload: dict[str, Any] = {

        "model": model,

        "messages": messages,

        "temperature": 0.2,

    }

    if tools:

        payload["tools"] = tools

        payload["tool_choice"] = "auto"



    response = requests.post(

        f"{base_url}/chat/completions",

        headers=headers,

        json=payload,

        timeout=REQUEST_TIMEOUT,

    )

    if not response.ok:
        _raise_llm_http_error(response)

    return response.json()


def _llm_http_error_details(response: requests.Response) -> dict[str, Any]:
    message = response.text or f"HTTP {response.status_code}"
    code: str | None = None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            nested = payload.get("error")
            if isinstance(nested, dict):
                if nested.get("message"):
                    message = str(nested["message"])
                if nested.get("code"):
                    code = str(nested["code"])
            elif payload.get("message"):
                message = str(payload["message"])
            if code is None and payload.get("code"):
                code = str(payload["code"])
    except Exception:  # noqa: BLE001
        pass
    return {"message": message, "code": code, "source": "llm"}


def _llm_http_error_message(response: requests.Response) -> str:
    return str(_llm_http_error_details(response)["message"])


def _raise_llm_http_error(response: requests.Response) -> None:
    details = _llm_http_error_details(response)
    raise AiStreamError(
        str(details["message"]),
        source="llm",
        code=details.get("code"),
    )


def _iter_llm_chat_completion_stream(
    *,
    base_url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict[str, Any]],
) -> Iterator[str]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": True,
    }
    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
        stream=True,
    )
    if not response.ok:
        _raise_llm_http_error(response)

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content:
            yield str(content)


def iter_chat_completion_events(
    *,
    llm_api_base_url: str,
    llm_api_key: str | None,
    llm_model: str,
    messages: list[dict[str, str]],
    mcp_enabled: bool,
    mcp_server_url: str,
    mcp_bearer_token: str | None,
    agent_max_iterations: int | None = None,
    system_prompt: str | None = None,
) -> Iterator[dict[str, Any]]:
    if not llm_model or not llm_model.strip():
        raise ValueError("Model is required. Configure it in AI Connection settings.")

    base_url = normalize_llm_base_url(llm_api_base_url)
    headers = {
        "Content-Type": "application/json",
        **_auth_headers(llm_api_key),
    }

    user_messages = [m for m in messages if m.get("role") in {"user", "assistant"}]
    if not user_messages:
        raise ValueError("No messages provided")

    openai_tools: list[dict[str, Any]] | None = None
    uses_tool_proxy = False
    if mcp_enabled and mcp_server_url:
        yield {"type": "status", "message": "Loading Superset MCP tools..."}
        mcp_tools = mcp_list_tools(mcp_server_url, bearer_token=mcp_bearer_token)
        uses_tool_proxy = _uses_tool_search_proxy(mcp_tools)
        if uses_tool_proxy:
            openai_tools = mcp_tools_to_openai(mcp_tools)
        else:
            openai_tools = mcp_tools_to_openai(
                [tool for tool in mcp_tools if tool.get("name") not in SYNTHETIC_MCP_TOOLS]
            )

    resolved_system_prompt = _resolve_agent_system_prompt(system_prompt)
    payload_messages: list[dict[str, Any]] = [
        {"role": "system", "content": resolved_system_prompt},
        *[
            {"role": m["role"], "content": m["content"]}
            for m in user_messages
            if m.get("content")
        ],
    ]

    tools_used: list[str] = []
    charts_this_turn: list[dict[str, Any]] = []
    chart_counter = 0
    max_iterations = _resolve_agent_max_iterations(agent_max_iterations)
    model = llm_model.strip()

    yield {"type": "status", "message": "Thinking..."}

    for _ in range(max_iterations):
        data = _llm_chat_completion(
            base_url=base_url,
            headers=headers,
            model=model,
            messages=payload_messages,
            tools=openai_tools,
        )
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("LLM returned no choices")

        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []

        if tool_calls and mcp_enabled and mcp_server_url:
            payload_messages.append(message)
            for tool_call in tool_calls:
                fn = tool_call.get("function") or {}
                tool_name = fn.get("name", "")
                if not tool_name:
                    continue
                display_tool = tool_name
                try:
                    arguments = _parse_tool_arguments(fn.get("arguments"))
                except json.JSONDecodeError as ex:
                    arguments = {}
                    tool_result = f"Invalid tool arguments JSON: {ex}"
                else:
                    mcp_tool_name, mcp_arguments = _resolve_mcp_tool_invocation(
                        tool_name,
                        arguments,
                        uses_proxy=uses_tool_proxy,
                    )
                    if tool_name == "call_tool":
                        display_tool = str(mcp_arguments.get("name", "call_tool"))
                    yield {"type": "tool_start", "tool": display_tool}
                    try:
                        raw_result = mcp_call_tool(
                            mcp_server_url,
                            mcp_tool_name,
                            mcp_arguments,
                            bearer_token=mcp_bearer_token,
                        )
                        tool_result = _serialize_tool_result(raw_result)
                        tools_used.append(display_tool)
                        chart_payload = _extract_chart_payload(display_tool, raw_result)
                        if chart_payload:
                            chart_payload = {
                                **chart_payload,
                                "id": f"chart-{chart_counter}",
                            }
                            chart_counter += 1
                            charts_this_turn.append(chart_payload)
                            yield {"type": "chart", "chart": chart_payload}
                    except Exception as ex:  # noqa: BLE001
                        logger.warning("MCP tool %s failed: %s", tool_name, ex)
                        tool_result = f"Tool error: {ex}"
                    yield {"type": "tool_end", "tool": display_tool}

                payload_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id") or f"call_{uuid.uuid4().hex}",
                        "content": tool_result,
                    }
                )
            yield {"type": "status", "message": "Thinking..."}
            continue

        yield {"type": "status", "message": "Writing response..."}
        content_parts: list[str] = []
        for token in _iter_llm_chat_completion_stream(
            base_url=base_url,
            headers=headers,
            model=model,
            messages=payload_messages,
        ):
            content_parts.append(token)
            yield {"type": "token", "content": token}

        content = "".join(content_parts).strip()
        if not content:
            raise ValueError("LLM returned an empty response")

        yield {
            "type": "done",
            "content": content,
            "tools_used": tools_used,
            "charts": charts_this_turn,
        }
        return

    raise ValueError(
        f"Agent stopped after {max_iterations} tool rounds without a final answer."
    )





def _normalize_model_id(model_id: str) -> str:
    return model_id.removeprefix("models/").strip()


def _model_in_list(requested: str, models: list[str]) -> bool:
    req = _normalize_model_id(requested).lower()
    for model in models:
        model_id = _normalize_model_id(model).lower()
        if req == model_id or req in model_id or model_id in req:
            return True
    return False


def _probe_chat_model(
    base_url: str,
    headers: dict[str, str],
    model: str,
) -> tuple[bool, str]:
    """Verify a model works via a minimal chat completion."""
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
            timeout=45,
        )
        if response.ok:
            return True, ""
        return False, response.text or f"HTTP {response.status_code}"
    except Exception as ex:  # noqa: BLE001
        return False, str(ex)


def test_llm_connection(
    llm_api_base_url: str,
    llm_api_key: str | None,
    llm_model: str | None,
) -> dict[str, Any]:
    base_url = normalize_llm_base_url(llm_api_base_url)
    headers = _auth_headers(llm_api_key)
    response = requests.get(
        f"{base_url}/models",
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        return {
            "ok": False,
            "message": response.text or f"HTTP {response.status_code}",
        }

    data = response.json()
    models = [
        item.get("id")
        for item in data.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]

    if llm_model and llm_model.strip():
        model_name = llm_model.strip()
        if not _model_in_list(model_name, models):
            probe_ok, probe_error = _probe_chat_model(base_url, headers, model_name)
            if probe_ok:
                return {
                    "ok": True,
                    "message": (
                        f'LLM connected. Model "{model_name}" works '
                        f"({len(models)} model(s) listed by provider)."
                    ),
                    "models": models,
                }
            similar = [
                m
                for m in models
                if any(part in _normalize_model_id(m).lower() for part in model_name.lower().split("-")[:2])
            ][:5]
            hint = f" Try: {', '.join(similar)}" if similar else ""
            return {
                "ok": False,
                "message": (
                    f'Model "{model_name}" is not available.{hint} '
                    f"Provider error: {probe_error[:200]}"
                ),
                "models": models,
            }

    return {
        "ok": True,
        "message": (
            f"LLM API connected. {len(models)} model(s) available."
            if models
            else "LLM API connected."
        ),
        "models": models,
    }





def test_mcp_connection(

    mcp_server_url: str,

    mcp_bearer_token: str | None,

) -> dict[str, Any]:

    tools = mcp_list_tools(mcp_server_url, bearer_token=mcp_bearer_token)

    return {

        "ok": True,

        "message": f"MCP server connected. {len(tools)} tool(s) available.",

        "tool_count": len(tools),

    }





def chat_completion(
    *,
    llm_api_base_url: str,
    llm_api_key: str | None,
    llm_model: str,
    messages: list[dict[str, str]],
    mcp_enabled: bool,
    mcp_server_url: str,
    mcp_bearer_token: str | None,
    agent_max_iterations: int | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    content_parts: list[str] = []
    tools_used: list[str] = []
    for event in iter_chat_completion_events(
        llm_api_base_url=llm_api_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        messages=messages,
        mcp_enabled=mcp_enabled,
        mcp_server_url=mcp_server_url,
        mcp_bearer_token=mcp_bearer_token,
        agent_max_iterations=agent_max_iterations,
        system_prompt=system_prompt,
    ):
        event_type = event.get("type")
        if event_type == "token":
            content_parts.append(str(event.get("content", "")))
        elif event_type == "done":
            return {
                "content": str(event.get("content", "")).strip() or "".join(content_parts).strip(),
                "tools_used": event.get("tools_used", tools_used),
            }
    raise ValueError("Chat ended without a final response")



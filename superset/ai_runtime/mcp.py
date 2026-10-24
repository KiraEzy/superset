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
"""FastMCP client adapter; authentication is connection-specific and never ambient."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
import time
from contextlib import AsyncExitStack
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from superset.utils import json

from .contracts import AiRuntimeError, Tool
from .policy import namespace, schema_validator

# Each process keeps a short-lived bounded discovery cache. Connection versions
# and credential fingerprints invalidate grants without retaining raw secrets.
_DISCOVERY: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}


def authentication_rejected(error: BaseException) -> bool:
    """Inspect typed HTTP status only; never parse or expose exception bodies."""
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) == 401 or any(
        authentication_rejected(child) for child in getattr(error, "exceptions", [])
    )


def dump(value: Any) -> Any:
    """Convert MCP/Pydantic objects using their wire aliases."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if is_dataclass(value) and not isinstance(value, type):
        return dump(asdict(value))
    if isinstance(value, dict):
        return {key: dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [dump(item) for item in value]
    return value


def normalize_result(value: Any) -> dict[str, Any]:
    """Retain all MCP blocks and honor isError, including text-backed Superset JSON."""
    raw = dump(value)
    if not isinstance(raw, dict):
        raw = {"content": [{"type": "text", "text": str(raw)}]}
    structured = raw.get("structuredContent", raw.get("structured_content"))
    blocks = [dump(block) for block in raw.get("content", [])]
    if structured is None:
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    structured = json.loads(block.get("text", ""))
                except (TypeError, ValueError):
                    continue
                if isinstance(structured, (dict, list)):
                    break
                structured = None
    if structured is None and ("success" in raw or "form_data" in raw):
        structured = raw
    error = bool(raw.get("isError", raw.get("is_error", False)))
    if isinstance(structured, dict) and structured.get("success") is False:
        error = True
    if any(
        isinstance(block, dict)
        and block.get("type") == "text"
        and str(block.get("text", "")).startswith(
            ("Error:", "Tool error:", "Validation error")
        )
        for block in blocks
    ):
        error = True
    return {
        "isError": error,
        "content": blocks,
        "structuredContent": structured,
        "structureSource": "native"
        if raw.get("structuredContent", raw.get("structured_content")) is not None
        else "client_parsed",
        "raw": raw,
    }


async def validate_url(connection: dict[str, Any]) -> None:
    """Reject credential URLs and private network targets unless admin-approved."""
    parsed = urlparse(connection.get("url", ""))
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise AiRuntimeError("Invalid MCP connection URL", code="invalid_connection")
    if connection.get("allow_private") is True:
        return
    if parsed.scheme != "https":
        raise AiRuntimeError(
            "External MCP connections require HTTPS", code="invalid_connection"
        )
    addresses = await asyncio.to_thread(
        socket.getaddrinfo,
        parsed.hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )
    if not addresses or any(
        not ipaddress.ip_address(item[4][0]).is_global for item in addresses
    ):
        raise AiRuntimeError(
            "Private MCP targets require administrator review",
            code="private_connection",
        )


class MCPPool:
    """Own all FastMCP client contexts for one turn."""

    def __init__(self, elicitation_handler: Any = None) -> None:
        self.stack = AsyncExitStack()
        self.clients: dict[str, Any] = {}
        self.proxied: set[tuple[str, str]] = set()
        self.transports: dict[str, Any] = {}
        self.refresh_auth: Any = None
        self.instructions: list[dict[str, str]] = []
        self.elicitation_handler = elicitation_handler

    async def __aenter__(self) -> MCPPool:
        await self.stack.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stack.__aexit__(*args)

    async def discover(  # noqa: C901 - execution state machine
        self, connections: list[dict[str, Any]], refresh_auth: Any
    ) -> list[Tool]:  # noqa: C901 - explicit execution state machine
        """Discover full schemas; hide synthetic dispatchers that bypass review."""
        try:
            from fastmcp import Client  # pylint: disable=import-outside-toplevel
            from fastmcp.client.transports import (
                StreamableHttpTransport,  # pylint: disable=import-outside-toplevel
            )
        except ImportError as ex:
            raise AiRuntimeError(
                "FastMCP client is unavailable",
                code="mcp_client_unavailable",
                source="mcp",
            ) from ex
        tools = []
        self.refresh_auth = refresh_auth
        for connection in connections:
            await validate_url(connection)
            # refresh_auth supplies only an explicit Focal access token, never cookies.
            token = (
                refresh_auth()
                if connection.get("is_focal")
                else connection.get("bearer_token")
            )
            if not token:
                token = connection.get("bearer_token")
            headers = {"Authorization": f"Bearer {token}"} if token else {}

            def client_factory(
                headers: Any = None,
                timeout: Any = None,
                auth: Any = None,
                _explicit_headers: Any = headers,
                _connection: Any = connection,
                **kwargs: Any,
            ) -> Any:
                import httpx  # pylint: disable=import-outside-toplevel

                async def validate_request(request: Any) -> None:
                    await validate_url({**_connection, "url": str(request.url)})
                    if (
                        urlparse(str(request.url)).netloc
                        != urlparse(_connection["url"]).netloc
                    ):
                        raise AiRuntimeError(
                            "MCP destination changed", code="destination_changed"
                        )
                    credential_refresh = _connection.get("credential_refresh")
                    current_token = (
                        self.refresh_auth()
                        if _connection.get("is_focal")
                        else (
                            credential_refresh()
                            if callable(credential_refresh)
                            else _connection.get("bearer_token")
                        )
                    )
                    if current_token:
                        request.headers["Authorization"] = f"Bearer {current_token}"
                    else:
                        request.headers.pop("Authorization", None)

                # Never allow a redirect to forward connection credentials elsewhere.
                # Ignore FastMCP ambient HTTP auth; only this connection's token is
                # used.
                return httpx.AsyncClient(
                    headers=_explicit_headers,
                    timeout=timeout or 120,
                    auth=auth,
                    follow_redirects=False,
                    trust_env=False,
                    event_hooks={"request": [validate_request]},
                )

            transport = StreamableHttpTransport(
                connection["url"], headers=headers, httpx_client_factory=client_factory
            )
            try:
                client = await self.stack.enter_async_context(
                    Client(
                        transport,
                        elicitation_handler=self.elicitation_handler,
                        timeout=300,
                    )
                )
            except Exception as ex:
                if authentication_rejected(ex):
                    raise AiRuntimeError(
                        "The MCP account rejected authentication; reconnect it",
                        code="connection_auth",
                        source="mcp",
                    ) from ex
                raise
            initialized = getattr(client, "initialize_result", None)
            guidance = getattr(initialized, "instructions", None)
            if guidance:
                self.instructions.append(
                    {"connection_id": str(connection["id"]), "instructions": guidance}
                )
            self.clients[str(connection["id"])] = client
            self.transports[str(connection["id"])] = transport
            cache_key = (
                connection.get("user_id"),
                connection.get("post_id"),
                connection["id"],
                connection.get("version"),
                connection["url"],
                hashlib.sha256(str(token or "").encode()).hexdigest(),
            )
            cached = _DISCOVERY.get(cache_key)
            if cached and cached[0] > time.monotonic():
                listed = cached[1]
            else:
                listed = [dump(item) for item in await client.list_tools()]
                if len(_DISCOVERY) >= 256:
                    _DISCOVERY.clear()
                _DISCOVERY[cache_key] = (time.monotonic() + 30, listed)
            names = {item["name"] for item in listed}
            if {"search_tools", "call_tool"}.issubset(names):
                trusted_catalog = connection.get("tool_catalog") or []
                if connection.get("is_focal"):
                    catalog_path = Path(__file__).with_name("focal_catalog.json")
                    if catalog_path.exists():
                        trusted_catalog = json.loads(
                            catalog_path.read_text(encoding="utf-8")
                        ).get("tools", [])
                # Metadata searches do not grant effects: only trusted schemas may
                # become callable aliases, and server visibility must confirm names.
                semaphore = asyncio.Semaphore(4)

                async def inspect_entry(
                    entry: dict[str, Any],
                    client: Any = client,
                    semaphore: Any = semaphore,
                    connection: Any = connection,
                ) -> dict[str, Any] | None:
                    if not isinstance(entry.get("inputSchema"), dict) or entry.get(
                        "name"
                    ) in {"search_tools", "call_tool"}:
                        return None
                    async with semaphore:
                        found = normalize_result(
                            await client.call_tool(
                                "search_tools",
                                {"query": entry["name"]},
                                raise_on_error=False,
                            )
                        )
                    data = found.get("structuredContent")
                    if isinstance(data, dict):
                        data = data.get("tools", data.get("results", []))
                    if (
                        not found["isError"]
                        and isinstance(data, list)
                        and any(
                            isinstance(item, dict) and item.get("name") == entry["name"]
                            for item in data
                        )
                    ):
                        self.proxied.add((str(connection["id"]), entry["name"]))
                        return entry
                    return None

                inspected = await asyncio.gather(
                    *(
                        inspect_entry(entry)
                        for entry in trusted_catalog
                        if entry.get("name") not in names
                    )
                )
                listed.extend(entry for entry in inspected if entry is not None)
            for item in listed:
                raw = dump(item)
                name = raw["name"]
                if name in {"call_tool", "search_tools"}:
                    continue
                reviewed = connection.get("reviewed_tools", {}).get(name, "unknown")
                if isinstance(reviewed, dict):
                    reviewed = reviewed.get("effect", "unknown")
                schema_validator(raw.get("inputSchema", {}))
                advertised = namespace(str(connection["id"]), name)
                tools.append(
                    Tool(
                        advertised,
                        name,
                        connection,
                        raw.get("inputSchema", {}),
                        raw.get("description", ""),
                        reviewed,
                        raw.get("annotations") or {},
                    )
                )
        if len({tool.name for tool in tools}) != len(tools):
            raise AiRuntimeError("Duplicate tool aliases", code="duplicate_tools")
        return tools

    async def call(self, tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call exactly the reviewed target; FastMCP preserves session lifecycle."""
        client = self.clients[str(tool.connection["id"])]
        await validate_url(tool.connection)
        if tool.connection.get("is_focal") and self.refresh_auth:
            token = self.refresh_auth()
            if token:
                transport = self.transports[str(tool.connection["id"])]
                # FastMCP 3.1's transport reads these explicit headers on each
                # operation. Do not mutate ambient browser/session credentials.
                if isinstance(getattr(transport, "headers", None), dict):
                    transport.headers["Authorization"] = f"Bearer {token}"
        name = tool.original_name
        if (str(tool.connection["id"]), name) in self.proxied:
            arguments = {"name": name, "arguments": arguments}
            name = "call_tool"
        try:
            return normalize_result(
                await client.call_tool(name, arguments, raise_on_error=False)
            )
        except Exception as ex:
            if authentication_rejected(ex):
                raise AiRuntimeError(
                    "The MCP account rejected authentication; reconnect it",
                    code="connection_auth",
                    source="mcp",
                ) from ex
            raise

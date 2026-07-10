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

"""Unit tests for RbacToolListFilterMiddleware (tools/list RBAC filtering).

Self-contained (lightweight Flask app + asyncio.run) so Docker runs work
without the full unit-test conftest / pytest-asyncio stack.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from flask import Flask, g

CLASS_PERMISSION_ATTR = "_class_permission_name"
METHOD_PERMISSION_ATTR = "_method_permission_name"


def _make_tool_fn(name: str, class_perm: str, method_perm: str = "read") -> Any:
    """Callable stub with FAB-style permission attrs."""

    def fn() -> None:
        pass

    fn.__name__ = name
    setattr(fn, CLASS_PERMISSION_ATTR, class_perm)
    setattr(fn, METHOD_PERMISSION_ATTR, method_perm)
    return fn


def _make_tool(name: str, class_perm: str, method_perm: str = "read") -> SimpleNamespace:
    """Minimal FastMCP Tool-like stub with ``name`` and ``fn``."""
    return SimpleNamespace(
        name=name,
        fn=_make_tool_fn(name, class_perm, method_perm),
    )


def _flask_app() -> Flask:
    app = Flask("test_rbac_list_tools")
    app.config["MCP_AUTH_ENABLED"] = False
    app.config["MCP_RBAC_ENABLED"] = True
    return app


def test_filters_out_unauthorized_tool() -> None:
    """tools/list omits tools where check_tool_permission returns False."""
    from superset.mcp_service.middleware import RbacToolListFilterMiddleware

    allowed = _make_tool("list_charts", "Chart")
    denied = _make_tool("list_datasets", "Dataset")
    tools = [allowed, denied]

    async def call_next(_context: Any) -> list[Any]:
        return tools

    def fake_check(target: Any) -> bool:
        return getattr(target, "__name__", None) != "list_datasets"

    app = _flask_app()
    middleware = RbacToolListFilterMiddleware()

    async def _run() -> list[Any]:
        with app.app_context():
            g.user = MagicMock(username="alice")
            with patch(
                "superset.mcp_service.auth.check_tool_permission",
                side_effect=fake_check,
            ):
                return await middleware.on_list_tools(MagicMock(), call_next)

    result = asyncio.run(_run())
    names = [t.name for t in result]
    assert "list_charts" in names
    assert "list_datasets" not in names


def test_keeps_all_tools_when_permitted() -> None:
    """tools/list keeps every tool when check_tool_permission allows all."""
    from superset.mcp_service.middleware import RbacToolListFilterMiddleware

    tools = [
        _make_tool("list_charts", "Chart"),
        _make_tool("list_datasets", "Dataset"),
    ]

    app = _flask_app()
    middleware = RbacToolListFilterMiddleware()

    async def _run() -> list[Any]:
        with app.app_context():
            g.user = MagicMock(username="alice")
            with patch(
                "superset.mcp_service.auth.check_tool_permission",
                return_value=True,
            ):
                return await middleware.on_list_tools(
                    MagicMock(), AsyncMock(return_value=tools)
                )

    result = asyncio.run(_run())
    assert [t.name for t in result] == ["list_charts", "list_datasets"]


def test_fail_closed_when_auth_enabled_and_no_user() -> None:
    """With MCP_AUTH_ENABLED and no g.user, return empty list."""
    from superset.mcp_service.middleware import RbacToolListFilterMiddleware

    tools = [_make_tool("list_charts", "Chart")]
    app = _flask_app()
    app.config["MCP_AUTH_ENABLED"] = True
    middleware = RbacToolListFilterMiddleware()

    async def _run() -> list[Any]:
        with app.app_context():
            g.pop("user", None)
            with patch(
                "superset.mcp_service.auth._setup_user_context",
                side_effect=ValueError("no token"),
            ):
                return await middleware.on_list_tools(
                    MagicMock(), AsyncMock(return_value=tools)
                )

    result = asyncio.run(_run())
    assert result == []


def test_registered_in_middleware_list() -> None:
    """RbacToolListFilterMiddleware is in build_middleware_list()."""
    from superset.mcp_service.middleware import RbacToolListFilterMiddleware
    from superset.mcp_service.server import build_middleware_list

    middleware_list = build_middleware_list()
    assert any(isinstance(m, RbacToolListFilterMiddleware) for m in middleware_list)


def test_mcp_auth_hook_preserves_permission_metadata() -> None:
    """mcp_auth_hook copies RBAC attrs onto the registered wrapper (no __wrapped__)."""
    from superset.mcp_service.auth import (
        CLASS_PERMISSION_ATTR,
        METHOD_PERMISSION_ATTR,
        mcp_auth_hook,
    )
    from superset.mcp_service.middleware import RbacToolListFilterMiddleware

    def list_datasets() -> None:
        """List datasets."""

    setattr(list_datasets, CLASS_PERMISSION_ATTR, "Dataset")
    setattr(list_datasets, METHOD_PERMISSION_ATTR, "read")

    wrapped = mcp_auth_hook(list_datasets)
    assert getattr(wrapped, CLASS_PERMISSION_ATTR) == "Dataset"
    assert getattr(wrapped, METHOD_PERMISSION_ATTR) == "read"
    assert not hasattr(wrapped, "__wrapped__")

    tool = SimpleNamespace(name="list_datasets", fn=wrapped)
    app = _flask_app()
    middleware = RbacToolListFilterMiddleware()

    def fake_check(target: Any) -> bool:
        # Real list path: attrs must be on the wrapper FastMCP registers.
        return getattr(target, CLASS_PERMISSION_ATTR, None) != "Dataset"

    async def _run() -> list[Any]:
        with app.app_context():
            g.user = MagicMock(username="viewer")
            with patch(
                "superset.mcp_service.auth.check_tool_permission",
                side_effect=fake_check,
            ):
                return await middleware.on_list_tools(
                    MagicMock(), AsyncMock(return_value=[tool])
                )

    result = asyncio.run(_run())
    assert result == []

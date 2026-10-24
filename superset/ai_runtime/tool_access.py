# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Administrator Chat tool restrictions, additional to native MCP authorization."""

from typing import Any

from flask import g

from superset import security_manager
from superset.ai_runtime.contracts import AiRuntimeError


def normalize_policy(value: Any) -> dict[str, dict[str, list[str]]]:
    """Validate an allowlist without interpreting it as a permission grant."""
    if not isinstance(value, dict) or set(value) - {"roles", "users"}:
        raise ValueError("Tool access must contain roles and users mappings")
    result: dict[str, dict[str, list[str]]] = {"roles": {}, "users": {}}
    for kind in result:
        rules = value.get(kind, {})
        if not isinstance(rules, dict) or len(rules) > 5000:
            raise ValueError("Invalid tool access rules")
        for principal, tools in rules.items():
            if (
                not isinstance(principal, str)
                or not principal.strip()
                or len(principal) > 128
                or not isinstance(tools, list)
                or len(tools) > 256
                or any(not isinstance(t, str) or not t or len(t) > 128 for t in tools)
            ):
                raise ValueError("Each role or user must map to a list of tool names")
            result[kind][principal] = sorted(set(tools))
    return result


def allowed_tools(
    policy: dict[str, dict[str, list[str]]], username: str, roles: set[str]
) -> set[str] | None:
    """Union matching role allowlists, then narrow them by an explicit user rule."""
    matching = [set(tools) for name, tools in policy["roles"].items() if name in roles]
    allowed = set().union(*matching) if matching else None
    if username in policy["users"]:
        user_tools = set(policy["users"][username])
        allowed = user_tools if allowed is None else allowed & user_tools
    return allowed


def current_tool_allowed(name: str) -> bool:
    """Load current rules and active-post roles at discovery and dispatch time."""
    from superset.views.ai.config_store import resolve_active_config

    user = getattr(g, "user", None)
    if not user:
        return False
    policy = normalize_policy(resolve_active_config().get("mcpToolAccess", {}))
    roles = {role.name for role in security_manager.get_user_roles(user)}
    allowed = allowed_tools(policy, user.username, roles)
    return allowed is None or name in allowed


def authorize_tool(name: str) -> None:
    """Fail before dispatch when an administrator revoked Chat tool access."""
    if not current_tool_allowed(name):
        raise AiRuntimeError(
            "This operation is unavailable under your administrator's tool policy.",
            code="tool_access_denied",
            source="authorization",
        )

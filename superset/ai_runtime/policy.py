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
"""Argument-aware BI authorization. Tool output never changes grants."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from superset.utils import json

from .contracts import AiRuntimeError, Tool

# Reviewed client policy, deliberately independent of server annotations.
FOCAL_READ = frozenset(
    {
        "health_check",
        "get_instance_info",
        "get_chart_preview",
        "get_chart_type_schema",
        "open_sql_lab_with_context",
        "list_databases",
        "list_datasets",
        "get_dataset_info",
        "get_database_info",
        "list_charts",
        "get_chart_info",
        "list_dashboards",
        "get_dashboard_info",
        "get_chart_data",
        "get_chart_config",
        "get_schema",
        "get_table_schema",
        "list_tables",
        "list_schemas",
        "generate_explore_link",
        "update_chart_preview",
        "get_available_chart_types",
        "get_chart_type_config",
    }
)
FOCAL_WRITE = frozenset(
    {
        "generate_chart",
        "generate_dashboard",
        "update_chart",
        "add_chart_to_existing_dashboard",
        "configure_dashboard",
        "create_virtual_dataset",
        "save_sql_query",
    }
)


def normalized_arguments(tool: Tool, arguments: Any) -> dict[str, Any]:
    """Apply schema wrappers, preview defaults and bounded Focal discovery reads."""
    if not isinstance(arguments, dict):
        raise AiRuntimeError(
            "Tool arguments must be a JSON object", code="invalid_arguments"
        )
    args = json.loads(json.dumps(arguments, allow_nan=False))
    props = tool.schema.get("properties", {})
    if "request" in props and "request" not in args:
        args = {"request": args}
    body = args.get("request", args)
    if tool.connection.get("is_focal") and tool.original_name == "generate_chart":
        body.setdefault("save_chart", False)
    if tool.connection.get("is_focal") and tool.original_name == "update_chart":
        body.setdefault("generate_preview", True)
    validate_arguments(tool.schema, args)
    if tool.connection.get("is_focal") and tool.original_name in {
        "list_datasets",
        "list_charts",
        "list_dashboards",
    }:
        requested_size = body.setdefault("page_size", 10)
        if requested_size > 25:
            # Choose a divisor so the smaller page starts at exactly the requested
            # offset. Effective arguments are returned to the model, which must
            # continue pagination using the actual page size.
            size = max(n for n in range(1, 26) if requested_size % n == 0)
            body["page"] = (body.get("page", 1) - 1) * requested_size // size + 1
            body["page_size"] = size
        if tool.original_name == "list_datasets" and not body.get("select_columns"):
            body["select_columns"] = [
                "id",
                "table_name",
                "schema",
                "database_name",
                "description",
            ]
        validate_arguments(tool.schema, args)
    return args


def schema_validator(schema: dict[str, Any]) -> Any:
    """Reject unsupported schemas before advertising or resolving any references."""
    try:
        from jsonschema import validators  # pylint: disable=import-outside-toplevel
    except ImportError as ex:
        raise AiRuntimeError(
            "JSON Schema validation is unavailable", code="schema_validator_unavailable"
        ) from ex
    try:

        def inspect(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"$ref", "$dynamicRef"} and (
                        not isinstance(child, str) or not child.startswith("#")
                    ):
                        raise ValueError("Remote schema references are unsupported")
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        inspect(schema)
        cls = (
            validators.validator_for(schema, default=None)
            if "$schema" in schema
            else validators.validator_for(schema)
        )
        if cls is None:
            raise ValueError("Unsupported JSON Schema dialect")
        cls.check_schema(schema)
        return cls(schema)
    except Exception as ex:
        raise AiRuntimeError(
            "The connection supplies an unsupported tool schema",
            code="unsupported_schema",
        ) from ex


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Validate arguments against the complete original tool schema."""
    validator = schema_validator(schema)
    try:
        validator.validate(arguments)
    except Exception as ex:
        error = AiRuntimeError(
            "Tool arguments do not match its original input schema",
            code="invalid_arguments",
        )
        error.validation = {
            "path": list(getattr(ex, "absolute_path", [])),
            "rule": getattr(ex, "validator", None),
            "message": str(getattr(ex, "message", "Invalid arguments")),
        }
        raise error from ex


def effect_for(tool: Tool, args: dict[str, Any]) -> str:
    """Classify effective behavior, treating unknown operations conservatively."""
    if tool.connection.get("is_focal"):
        body = args.get("request", args)
        if tool.original_name == "generate_chart" and body.get("save_chart") is False:
            return "read"
        if (
            tool.original_name == "update_chart"
            and body.get("generate_preview", True) is True
        ):
            return "read"
        if tool.original_name == "configure_dashboard" and (
            body.get("overview_layout")
            or body.get("remove_chart_ids")
            or body.get("remove_filter_ids")
        ):
            return "destructive"
        if tool.original_name == "execute_sql":
            # Even SELECT can invoke side-effecting functions: never infer safety from
            # SQL.
            return "unknown"
        if tool.original_name in FOCAL_READ:
            return "read"
        if tool.original_name in FOCAL_WRITE:
            return "write"
    return tool.effect if tool.effect in {"read", "write", "destructive"} else "unknown"


def fingerprint(tool: Tool, args: dict[str, Any]) -> str:
    """Bind one confirmation to an immutable connection/tool/argument identity."""
    payload = {
        "connection_id": str(tool.connection["id"]),
        "url": tool.connection.get("url"),
        "connection_version": tool.connection.get("version"),
        "user_id": tool.connection.get("user_id"),
        "post_id": tool.connection.get("post_id"),
        "schema": tool.schema,
        "tool": tool.original_name,
        "arguments": args,
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def authorized(tool: Tool, args: dict[str, Any], scopes: list[Any]) -> bool:
    """Require reviewed effects and server-created, argument-bound approval scopes."""
    if effect_for(tool, args) == "read":
        return True
    key = fingerprint(tool, args)
    # Strings are accepted only as exact fingerprints, never tool-name wildcards.
    return any(
        scope == key
        or (
            isinstance(scope, dict)
            and scope.get("fingerprint") == key
            and scope.get("approved") is True
        )
        for scope in scopes
    )


def namespace(connection_id: str, name: str) -> str:
    """Create a deterministic provider-compatible name without alias collisions."""
    prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", connection_id)[:16]
    suffix = hashlib.sha256(f"{connection_id}:{name}".encode()).hexdigest()[:10]
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:32]
    return f"{prefix}__{safe}_{suffix}"


def explicit_intent(tool: Tool, args: dict[str, Any], state: dict[str, Any]) -> bool:  # noqa: C901 - explicit execution state machine
    """Recognize bounded direct BI instructions; ambiguous actions need approval.

    Interpretation cannot grant resource access: native permissions are rechecked
    separately. Save-followup scope is matched to the actual prior preview call.
    """
    if not tool.connection.get("is_focal") or effect_for(tool, args) != "write":
        return False
    text = str(state.get("input_text", "")).strip().lower()
    text = re.sub(r"^(please|can you|could you|i want you to)\s+", "", text)
    if not re.match(r"^(save|update|change|modify|add|create|build|configure)\b", text):
        return False
    body = args.get("request", args)
    if tool.original_name == "generate_chart" and re.match(r"^save\b", text):
        for message in reversed(state.get("messages", [])):
            for call in message.get("tool_calls", []):
                if call.get("function", {}).get("name") != tool.name:
                    continue
                try:
                    previous = json.loads(call["function"].get("arguments", "{}"))
                    previous = previous.get("request", previous)
                    candidate = {**body, "save_chart": False}
                    previous = {**previous, "save_chart": False}
                    if previous == candidate:
                        return True
                except (ValueError, TypeError):
                    continue
        return False
    if tool.original_name == "generate_chart":
        return bool(
            re.search(r"\b(and save|save it|save the chart|save this chart)\b", text)
        )
    if tool.original_name in {
        "update_chart",
        "configure_dashboard",
        "add_chart_to_existing_dashboard",
    }:
        target = body.get("identifier", body.get("dashboard_id"))
        return target is not None and bool(
            re.search(rf"\b{re.escape(str(target))}\b", text)
        )
    if tool.original_name == "generate_dashboard":
        name = body.get(
            "dashboard_title", body.get("dashboard_name", body.get("title", ""))
        )
        return bool(name and "dashboard" in text and str(name).lower() in text)
    if tool.original_name == "save_sql_query":
        return bool(text.startswith("save") and ("query" in text or "sql" in text))
    if tool.original_name == "create_virtual_dataset":
        name = body.get("dataset_name", "")
        return bool(name and "dataset" in text and str(name).lower() in text)
    return False

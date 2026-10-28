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
"""Application decisions around public SDK approval interruptions."""

from typing import Any

from superset.utils import json

from .context import digest
from .contracts import AiRuntimeError
from .policy import (
    authorized,
    explicit_intent,
    fingerprint,
    normalized_arguments,
    validate_arguments,
)


def prepare_approvals(  # noqa: C901
    sdk_state: Any,
    state: dict[str, Any],
    cp: dict[str, Any],
    catalog: dict[str, Any],
    helper_schemas: dict[str, Any],
    session_items: list[Any],
) -> dict[str, Any] | None:  # noqa: C901
    """Resolve policy-approved calls or return one exact user interaction."""
    previous = cp.get("pending_request") or {}
    response = state.pop("pending_response", {}) or {}
    for approval in sdk_state.get_interruptions():
        raw = approval.raw_item.model_dump()
        name, call_id = raw["name"], raw["call_id"]
        try:
            args = json.loads(raw["arguments"])
            target = catalog.get(name)
            if target:
                args = normalized_arguments(target, args)
                validate_arguments(target.schema, args)
                binding = fingerprint(target, args)
            else:
                validate_arguments(helper_schemas[name], args)
                binding = digest(
                    {
                        "tool": name,
                        "args": args,
                        "user": state.get("user_id"),
                        "post": state.get("post_id"),
                    }
                )
        except (ValueError, KeyError, TypeError, AiRuntimeError):
            sdk_state.reject(approval)
            continue
        if name not in cp.get("offered_tools", []):
            sdk_state.reject(approval)
            continue
        previous_binding = cp.setdefault("bindings", {}).get(call_id)
        changed_binding = previous_binding is not None and previous_binding != binding
        cp["bindings"][call_id] = binding
        responding = (
            previous.get("call_id") == call_id
            and previous.get("fingerprint") == binding
        )
        if name == "ask_user":
            answer = response.get("input") if responding else None
            if isinstance(answer, str) and answer.strip():
                cp.setdefault("answers", {})[call_id] = answer.strip()
                sdk_state.approve(approval)
                continue
            return {
                "kind": "clarification",
                "call_id": call_id,
                "question": args["question"],
                "message": args["question"],
                "options": args.get("options", []),
                "fingerprint": binding,
            }
        if target is None:
            sdk_state.approve(approval)
            continue
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": item["name"], "arguments": item["arguments"]}}
                ],
            }
            for item in session_items
            if item.get("type") == "function_call"
        ]
        record = cp.get("calls", {}).get(call_id, {})
        if record.get("status") == "in_progress" and record.get("effect") != "read":
            raise AiRuntimeError(
                "Operation outcome needs review", code="uncertain_write"
            )
        cached = (
            record.get("status") == "completed" and record.get("fingerprint") == binding
        )
        repeated = any(
            r.get("fingerprint") == binding
            and r.get("effect") != "read"
            and r.get("status") == "completed"
            for r in cp.get("calls", {}).values()
        )
        permitted = (
            (state.get("approval_mode", "ask") == "full_access" and not repeated)
            or cached
            or (
                (not record or record.get("status") == "not_dispatched")
                and cp.get("grants", {}).get(call_id) == binding
                and not changed_binding
            )
            or authorized(
                target, args, state.get("approved_scopes", []) if responding else []
            )
            or (
                not changed_binding
                and not repeated
                and explicit_intent(target, args, {**state, "messages": messages})
            )
        )
        if responding and response.get("decision") == "decline":
            cp.setdefault("denials", {})[call_id] = binding
            sdk_state.reject(approval)
        elif cp.get("denials", {}).get(call_id) == binding:
            sdk_state.reject(approval)
        elif permitted:
            cp.setdefault("grants", {})[call_id] = binding
            sdk_state.approve(approval)
        else:
            return {
                "kind": "approval",
                "call_id": call_id,
                "tool": name,
                "arguments": args,
                "fingerprint": binding,
                "schema_hash": target.schema_hash,
                "message": f"Approve {target.original_name}?",
            }
    cp["pending_request"] = None
    return None

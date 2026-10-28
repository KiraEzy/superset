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
"""Transactional SDK history operations used by branching and terminal recovery."""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from superset.utils import json

from .contracts import AiRuntimeError
from .evidence import bounded


def clone_prefix(  # noqa: C901
    database: Any,
    models: tuple[Any, Any],
    source_id: str,
    target_id: str,
    owner_id: int,
    post_id: int,
    boundary: int,
    artifacts: dict[str, Any],
) -> None:  # noqa: C901
    """Copy a completed, scoped SDK prefix inside the caller's branch transaction."""
    session, item = models
    source = (
        database.query(session)
        .filter_by(id=source_id, owner_id=owner_id, post_id=post_id)
        .one_or_none()
    )
    if source is None:
        raise AiRuntimeError("SDK branch source is unavailable", code="session_scope")
    rows = (
        database.query(item)
        .filter_by(session_id=source_id)
        .filter(item.position < boundary)
        .order_by(item.position)
        .all()
    )
    if len(rows) != boundary:
        raise AiRuntimeError("SDK branch boundary changed", code="session_conflict")
    values = [json.loads(row.payload) for row in rows]
    calls = {v["call_id"] for v in values if v.get("type") == "function_call"}
    results = {v["call_id"] for v in values if v.get("type") == "function_call_output"}
    if calls != results:
        raise AiRuntimeError("SDK branch has unresolved calls", code="session_conflict")
    database.add(
        session(
            id=target_id,
            owner_id=owner_id,
            post_id=post_id,
            binding=source.binding,
            revision=0,
        )
    )
    database.flush()

    def remap(value: Any) -> Any:
        if isinstance(value, str):
            return artifacts[value]["id"] if value in artifacts else value
        if isinstance(value, dict):
            return {
                k: (v if k.startswith("source_") else remap(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [remap(v) for v in value]
        return value

    for position, value in enumerate(values):
        field = (
            "arguments"
            if value.get("type") == "function_call"
            else "output"
            if value.get("type") == "function_call_output"
            else None
        )
        if field and isinstance(value.get(field), str):
            try:
                value[field] = json.dumps(remap(json.loads(value[field])))
            except (ValueError, TypeError):
                pass
        database.add(
            item(
                id=str(uuid5(NAMESPACE_URL, f"{target_id}:branch:{position}")),
                session_id=target_id,
                position=position,
                payload=json.dumps(value),
            )
        )


def seal_terminal(
    database: Any, models: tuple[Any, Any], turn: Any, checkpoint: dict[str, Any]
) -> None:
    """Close orphan calls with recorded outcomes or explicit unknown/cancel markers."""
    session, item = models
    # This runs before the caller commits its terminal status/released active key.
    row = (
        database.query(session)
        .filter_by(
            id=checkpoint.get("sdk_session_id"),
            owner_id=turn.user_id,
            post_id=turn.post_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        return
    rows = (
        database.query(item).filter_by(session_id=row.id).order_by(item.position).all()
    )
    values = [json.loads(r.payload) for r in rows]
    outputs = {v["call_id"] for v in values if v.get("type") == "function_call_output"}
    pending = [
        v["call_id"]
        for v in values
        if v.get("type") == "function_call" and v["call_id"] not in outputs
    ]
    for offset, call_id in enumerate(pending):
        record = checkpoint.get("calls", {}).get(call_id, {})
        if record.get("status") == "completed":
            visible, truncated = bounded(record["result"], max_chars=10000)
            outcome = {
                "result": visible,
                "truncated": truncated,
                "evidence_ref": call_id,
            }
        else:
            outcome = {
                "isError": True,
                "message": (
                    "Execution ended without a recorded outcome. "
                    "Inspect any write before repeating it."
                ),
            }
        value = {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(outcome),
        }
        database.add(
            item(
                id=str(uuid5(NAMESPACE_URL, f"{turn.id}:terminal:{call_id}")),
                session_id=row.id,
                position=len(rows) + offset,
                payload=json.dumps(value),
            )
        )
    if pending:
        row.revision += 1


def image_reference_projection(
    database: Any, models: tuple[Any, Any], session_id: str, owner_id: int, post_id: int
) -> list[dict[str, Any]]:
    """Project only scoped SDK image IDs for attachment validation, not inference."""
    session, item = models
    if (
        database.query(session)
        .filter_by(id=session_id, owner_id=owner_id, post_id=post_id)
        .one_or_none()
        is None
    ):
        return []
    parts = []
    for row in (
        database.query(item).filter_by(session_id=session_id).order_by(item.position)
    ):
        value = json.loads(row.payload)
        content = value.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            url = part.get("image_url", "")
            if (
                part.get("type") == "input_image"
                and isinstance(url, str)
                and url.startswith("focal-image:")
            ):
                parts.append(
                    {"type": "image_ref", "image_id": url.removeprefix("focal-image:")}
                )
    return [{"role": "user", "content": parts}] if parts else []

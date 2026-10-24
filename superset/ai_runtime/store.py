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
"""Authoritative, post-scoped Chat ledger and transactional submission service."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from flask import g
from sqlalchemy.exc import IntegrityError

from superset import security_manager
from superset.ai_runtime import notifications, settings
from superset.extensions import db
from superset.models.ai_chat import AiChatMessage, AiChatSession
from superset.models.ai_runtime import (
    AiRuntimeArtifact,
    AiRuntimeEvent,
    AiRuntimeItem,
    AiRuntimeOutbox,
    AiRuntimeTurn,
)
from superset.utils import json

TERMINAL = frozenset({"completed", "cancelled", "failed"})


class RuntimeRequestError(ValueError):
    """A safe, structured API failure."""

    def __init__(
        self, message: str, status: int = 400, code: str = "invalid_request"
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def dumps(value: Any) -> str:
    """Serialize stored JSON consistently, including timestamp values."""
    return json.dumps(value, default=str, sort_keys=True)


def loads(value: str | None, default: Any = None) -> Any:
    """Decode a stored value; absence is different from malformed data."""
    return json.loads(value) if value else ({} if default is None else default)


def now() -> datetime:
    """Use naive UTC consistently with Superset metadata timestamps."""
    return datetime.utcnow()


def current_scope() -> tuple[int, int]:
    """Validate authenticated user and current post membership on every request."""
    user = getattr(g, "user", None)
    if not user or not getattr(user, "id", None) or getattr(user, "is_anonymous", True):
        raise RuntimeRequestError("Authentication required", 401, "unauthenticated")
    post_id = security_manager.get_active_post_id()
    if not post_id or int(post_id) not in {
        int(p.id) for p in security_manager.get_user_posts(user)
    }:
        raise RuntimeRequestError(
            "Select an assigned active post before using AI Chat", 403, "post_required"
        )
    return int(user.id), int(post_id)


def get_thread(thread_id: str, *, lock: bool = False) -> AiChatSession:
    """Find a conversation inside the current user/post boundary."""
    user_id, post_id = current_scope()
    try:
        identifier = UUID(thread_id)
    except (TypeError, ValueError) as ex:
        raise RuntimeRequestError("Conversation not found", 404, "not_found") from ex
    query = db.session.query(AiChatSession).filter(
        AiChatSession.uuid == identifier,
        AiChatSession.created_by_fk == user_id,
        AiChatSession.post_id == post_id,
        AiChatSession.runtime_version == 2,
    )
    thread = (query.with_for_update() if lock else query).one_or_none()
    if not thread:
        raise RuntimeRequestError("Conversation not found", 404, "not_found")
    return thread


def get_turn(turn_id: str, *, lock: bool = False) -> AiRuntimeTurn:
    """Never expose another post's turn through a guessed identifier."""
    user_id, post_id = current_scope()
    query = db.session.query(AiRuntimeTurn).filter_by(
        id=turn_id, user_id=user_id, post_id=post_id
    )
    turn = (query.with_for_update() if lock else query).one_or_none()
    if not turn:
        raise RuntimeRequestError("Turn not found", 404, "not_found")
    return turn


def validate_context(context: Any) -> list[dict[str, Any]]:
    """Resolve client references using native Superset resource authorization."""
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    if not isinstance(context, list) or len(context) > 20:
        raise RuntimeRequestError("Context must contain at most 20 resource references")
    models = {
        "chart": (Slice, security_manager.can_access_chart),
        "dashboard": (Dashboard, security_manager.can_access_dashboard),
        "dataset": (SqlaTable, security_manager.can_access_datasource),
    }
    resolved = []
    for ref in context:
        if not isinstance(ref, dict) or ref.get("type") not in models:
            raise RuntimeRequestError("Unsupported BI context reference")
        if isinstance(ref.get("id"), bool) or not isinstance(ref.get("id"), int):
            raise RuntimeRequestError("Resource IDs must be integers")
        model, permitted = models[ref["type"]]
        resource = db.session.query(model).get(ref["id"])
        if not resource or not permitted(resource):
            raise RuntimeRequestError(
                "Referenced BI resource is unavailable", 403, "context_denied"
            )
        filters = ref.get("filters", {})
        if not isinstance(filters, dict) or len(dumps(filters)) > 16000:
            raise RuntimeRequestError("Invalid context filters")
        resolved.append(
            {
                "type": ref["type"],
                "id": ref["id"],
                "filters": filters,
                "title": str(
                    getattr(resource, "slice_name", None)
                    or getattr(resource, "dashboard_title", None)
                    or getattr(resource, "table_name", ref["id"])
                ),
            }
        )
    return resolved


def history(thread: AiChatSession) -> list[dict[str, Any]]:
    """Reuse the last successful canonical transcript, including tool evidence."""
    prior = (
        db.session.query(AiRuntimeTurn)
        .filter_by(session_id=thread.id, status="completed")
        .order_by(AiRuntimeTurn.created_on.desc())
        .first()
    )
    if prior:
        return loads(prior.state_json).get("messages", [])
    return []


def submit(thread_id: str, data: dict[str, Any]) -> AiRuntimeTurn:  # noqa: C901 - explicit execution state machine
    """Persist input and dispatch together; deduplicate before any side effect."""
    if not settings.enabled():
        raise RuntimeRequestError(
            "New runtime submissions are disabled", 503, "runtime_disabled"
        )
    thread = get_thread(thread_id, lock=True)
    text = data.get("input")
    key = data.get("idempotency_key")
    if not isinstance(text, str) or not text.strip() or len(text) > 64000:
        raise RuntimeRequestError("Input must contain 1 to 64000 characters")
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise RuntimeRequestError("An idempotency key is required")
    if data.get("profile_id", "default") != "default":
        raise RuntimeRequestError("Unknown model profile")
    digest = hashlib.sha256(dumps(data).encode()).hexdigest()
    existing = (
        db.session.query(AiRuntimeTurn)
        .filter_by(session_id=thread.id, idempotency_key=key)
        .first()
    )
    if existing:
        if existing.input_hash != digest:
            raise RuntimeRequestError(
                "Idempotency key was used for different input",
                409,
                "idempotency_conflict",
            )
        return existing
    if db.session.query(AiRuntimeTurn).filter_by(active_key=str(thread.uuid)).first():
        raise RuntimeRequestError(
            "This conversation already has an active turn", 409, "turn_active"
        )
    from superset.views.ai.config_store import resolve_active_config

    user_id, post_id = current_scope()
    from superset.ai_runtime import images, model_catalog

    config = model_catalog.resolve(data.get("model_id"), resolve_active_config())
    config.update(image_user_id=user_id, image_post_id=post_id)
    connection_ids = ["focalbi"] if config.get("mcpEnabled") else []
    # Accept stale clients only when their choices match server-owned settings.
    if "connection_ids" in data and data["connection_ids"] != connection_ids:
        raise RuntimeRequestError("Connections are managed by your administrator")
    workflows = data.get("workflow_ids", [])
    from superset.ai_runtime.workflows import workflow_catalog, workflow_instructions

    known_workflows = {w["id"] for w in workflow_catalog()}
    if not isinstance(workflows, list) or any(
        not isinstance(w, str) or w not in known_workflows for w in workflows
    ):
        raise RuntimeRequestError("Unknown workflow selection")
    context = validate_context(data.get("context", []))
    from superset.views.ai.proxy import normalize_llm_base_url

    config["llmApiBaseUrl"] = normalize_llm_base_url(config["llmApiBaseUrl"])
    config["adapter"] = (
        config.get("llmAdapter", "chat_completions")
        if config.get("llmProvider") == "openai"
        else "chat_completions"
    )
    if data.get("adapter", config["adapter"]) != config["adapter"]:
        raise RuntimeRequestError(
            "Model configuration is managed by your administrator"
        )
    if not isinstance(config["adapter"], str) or config["adapter"] not in {
        "chat_completions",
        "responses",
    }:
        raise RuntimeRequestError("Unsupported model adapter")
    messages = history(thread)
    continuation = {}
    context_memory = {}
    previous_turn = (
        db.session.query(AiRuntimeTurn)
        .filter_by(session_id=thread.id, status="completed")
        .order_by(AiRuntimeTurn.created_on.desc())
        .first()
    )
    if previous_turn:
        previous_state = loads(previous_turn.state_json)
        context_memory = previous_state.get("checkpoint", {}).get("context_memory", {})
        prior_config = previous_state.get("config", {})
        if all(
            prior_config.get(field) == config.get(field)
            for field in (
                "llmModel",
                "llmApiBaseUrl",
                "adapter",
                "model_connection_id",
                "model_revision",
            )
        ):
            continuation = previous_state.get("checkpoint", {}).get("continuation", {})
        else:
            # Opaque provider fields cannot be forwarded to a different model.
            messages = [
                {
                    key: value
                    for key, value in message.items()
                    if key != "reasoning_content"
                }
                for message in messages
            ]
    attachment_refs = images.references(
        data.get("attachment_ids", []), messages, vision=bool(config.get("vision"))
    )
    for ref in attachment_refs:
        images.get(ref["id"]).bound = True
    turn = AiRuntimeTurn(
        id=str(uuid4()),
        session_id=thread.id,
        user_id=user_id,
        post_id=post_id,
        idempotency_key=key,
        input_hash=digest,
        active_key=str(thread.uuid),
        status="queued",
        state_json=dumps(
            {
                "config": config,
                "messages": messages,
                "input_text": text.strip(),
                "attachment_ids": [r["id"] for r in attachment_refs],
                "context": context,
                "connection_ids": connection_ids,
                "workflow_ids": workflows,
                "workflow_versions": {
                    w["id"]: w["version"]
                    for w in workflow_catalog()
                    if w["id"] in workflows
                },
                "workflow_instructions": workflow_instructions(workflows),
                "budgets": settings.limits(config.get("llmModel"), config),
                "approved_scopes": [],
                "checkpoint": {
                    "continuation": continuation,
                    "context_memory": context_memory,
                },
            }
        ),
    )
    try:
        db.session.add(turn)
        db.session.flush()
        message = AiChatMessage(session_id=thread.id, role="user", content=text.strip())
        message.extra = {"runtime_turn_id": turn.id, "attachments": attachment_refs}
        db.session.add(message)
        if not thread.messages:
            thread.title = text.strip()[:80]
        thread.changed_on = now()
        db.session.add(AiRuntimeOutbox(turn_id=turn.id))
        append_event(
            turn, "status", {"status": "queued", "message": "Queued"}, commit=False
        )
        db.session.commit()
        notifications.publish(turn.id)
    except IntegrityError as ex:
        db.session.rollback()
        same = (
            db.session.query(AiRuntimeTurn)
            .filter_by(session_id=thread.id, idempotency_key=key)
            .first()
        )
        if same and same.input_hash == digest:
            return same
        raise RuntimeRequestError(
            "Another turn was accepted concurrently", 409, "turn_active"
        ) from ex
    return turn


def append_event(
    turn: AiRuntimeTurn,
    event_type: str,
    payload: dict[str, Any],
    *,
    item_id: str | None = None,
    commit: bool = True,
) -> AiRuntimeEvent:
    """Increment sequence under a row lock and commit before notifying readers."""
    db.session.flush()
    locked = (
        db.session.query(AiRuntimeTurn).filter_by(id=turn.id).with_for_update().one()
    )
    locked.next_sequence += 1
    locked.changed_on = now()
    event = AiRuntimeEvent(
        turn_id=turn.id,
        sequence=locked.next_sequence,
        event_type=event_type,
        payload_json=dumps(payload),
        item_id=item_id,
    )
    db.session.add(event)
    if commit:
        db.session.commit()
        notifications.publish(turn.id)
    return event


def artifact_dict(row: AiRuntimeArtifact) -> dict[str, Any]:
    """Serialize a versioned, user-visible artifact."""
    payload = loads(row.payload_json)
    return {
        "id": row.id,
        "type": row.artifact_type,
        "title": row.title,
        "version": row.version,
        "payload": payload,
        "provenance": loads(row.provenance_json),
        "saved": bool(payload.get("slice_id") or payload.get("saved")),
    }


def activity_item(turn: AiRuntimeTurn, row: AiRuntimeItem) -> dict[str, Any]:
    """Serialize visible activity with truthful terminal state for old records too."""
    status = row.status
    if status == "running" and turn.status in TERMINAL:
        status = "cancelled" if turn.status == "cancelled" else "interrupted"
    return {
        "id": row.id,
        "kind": row.kind,
        "status": status,
        "payload": loads(row.payload_json),
    }


def work_activity(turn: AiRuntimeTurn, items: list[AiRuntimeItem]) -> dict[str, Any]:
    """Expose elapsed active work and visible activity, never private reasoning."""
    checkpoint = loads(turn.state_json).get("checkpoint", {})
    duration = checkpoint.get("active_seconds")
    return {
        "duration_seconds": max(0, float(duration))
        if isinstance(duration, (int, float))
        else None,
        "status": turn.status,
        "items": [
            activity_item(turn, row)
            for row in items
            if row.kind
            in {
                "tool",
                "reasoning_status",
                "reasoning_summary",
                "model_reasoning",
                "progress",
            }
        ],
    }


def snapshot(turn: AiRuntimeTurn) -> dict[str, Any]:
    """Return public state without exposing model credentials or internal leases."""
    thread = db.session.query(AiChatSession).get(turn.session_id)
    items = (
        db.session.query(AiRuntimeItem)
        .filter_by(turn_id=turn.id)
        .order_by(AiRuntimeItem.created_on, AiRuntimeItem.id)
        .all()
    )
    artifacts = (
        db.session.query(AiRuntimeArtifact)
        .filter_by(turn_id=turn.id)
        .order_by(AiRuntimeArtifact.created_on)
        .all()
    )
    public_items = [
        activity_item(turn, row) for row in items if row.kind not in {"user_input"}
    ]
    requests = [
        {"id": row.id, **loads(row.payload_json)}
        for row in items
        if row.kind == "request" and row.status == "pending"
    ]
    return {
        "id": turn.id,
        "thread_id": str(thread.uuid),
        "status": turn.status,
        "content": turn.content or "",
        "items": public_items,
        "activity": work_activity(turn, items),
        "artifacts": [artifact_dict(a) for a in artifacts],
        "pending_requests": requests,
        "last_sequence": turn.next_sequence,
        "error": loads(turn.error_json) if turn.error_json else None,
        "created_on": turn.created_on.isoformat() + "Z",
    }


def cancel(turn: AiRuntimeTurn) -> AiRuntimeTurn:
    """Cancellation is durable and never implies that a committed write was undone."""
    if turn.status in TERMINAL or turn.status == "cancelling":
        return turn
    live_request = turn.lease_owner is not None and turn.status == "waiting_input"
    if (
        turn.status in {"queued", "waiting_input", "waiting_approval", "needs_review"}
        and not live_request
    ):
        turn.status = "cancelled"
        turn.active_key = None
        for row in db.session.query(AiRuntimeItem).filter_by(
            turn_id=turn.id, kind="request", status="pending"
        ):
            row.status = "cancelled"
        append_event(turn, "turn_completed", {"status": "cancelled"}, commit=False)
    else:
        turn.status = "cancelling"
        append_event(
            turn,
            "status",
            {
                "status": "cancelling",
                "message": "Stopping; completed actions remain saved",
            },
            commit=False,
        )
    db.session.commit()
    notifications.publish(turn.id)
    return turn


def input_turn(turn: AiRuntimeTurn, data: dict[str, Any]) -> AiRuntimeTurn:  # noqa: C901 - explicit execution state machine
    """Persist deduplicated interaction input and bind approvals to one request."""
    if data.get("expected_turn_id") != turn.id:
        raise RuntimeRequestError("Active turn changed", 409, "turn_changed")
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise RuntimeRequestError("An idempotency key is required")
    existing = (
        db.session.query(AiRuntimeItem)
        .filter_by(turn_id=turn.id, kind="user_input", external_id=key)
        .first()
    )
    if existing:
        if (
            loads(existing.payload_json).get("submission_hash")
            != hashlib.sha256(dumps(data).encode()).hexdigest()
        ):
            raise RuntimeRequestError("Input key conflict", 409, "idempotency_conflict")
        return turn
    if turn.status in TERMINAL or turn.status in {"cancelling", "needs_review"}:
        raise RuntimeRequestError("Turn cannot accept input", 409, "turn_inactive")
    state = loads(turn.state_json)
    request_id = data.get("request_id")
    response = data.get("response", {})
    if request_id:
        pending = (
            db.session.query(AiRuntimeItem)
            .filter_by(id=request_id, turn_id=turn.id, kind="request", status="pending")
            .one_or_none()
        )
        if not pending:
            raise RuntimeRequestError(
                "Request is no longer pending", 409, "request_expired"
            )
        details = loads(pending.payload_json)
        if details.get("expires_at") and now().isoformat() > details[
            "expires_at"
        ].rstrip("Z"):
            raise RuntimeRequestError("Request expired", 409, "request_expired")
        if not isinstance(response, dict):
            raise RuntimeRequestError("Invalid response")
        if details.get("kind") == "approval":
            checkpoint_request = state.get("checkpoint", {}).get("pending_request", {})
            if checkpoint_request.get("fingerprint") != details.get("fingerprint"):
                raise RuntimeRequestError(
                    "The proposed operation changed; request a new approval",
                    409,
                    "approval_changed",
                )
            decision = response.get("decision")
            if decision not in {"accept", "decline"}:
                raise RuntimeRequestError("Choose accept or decline")
            if decision == "accept":
                fingerprint = details.get("fingerprint")
                if not fingerprint:
                    raise RuntimeRequestError(
                        "Approval has no verifiable action scope", 409
                    )
                state.setdefault("approved_scopes", []).append(fingerprint)
        pending.status = "completed"
        details["response"] = response
        pending.payload_json = dumps(details)
        state["pending_request"] = details
        state["pending_response"] = response
        if details.get("live_session"):
            turn.status = "running"
        else:
            turn.status = "queued"
            db.session.add(AiRuntimeOutbox(turn_id=turn.id))
    else:
        text = data.get("input")
        if (
            turn.status not in {"running", "queued"}
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 64000
        ):
            raise RuntimeRequestError("Steering requires text and an active turn", 409)
    db.session.add(
        AiRuntimeItem(
            turn_id=turn.id,
            kind="user_input",
            status="pending",
            external_id=key,
            payload_json=dumps(
                {
                    **data,
                    "submission_hash": hashlib.sha256(dumps(data).encode()).hexdigest(),
                }
            ),
        )
    )
    turn.state_json = dumps(state)
    append_event(
        turn,
        "status",
        {"status": turn.status, "message": "Input received"},
        commit=False,
    )
    db.session.commit()
    notifications.publish(turn.id)
    return turn


def branch_reply(
    thread: AiChatSession,
    turn_id: str,
    mode: str,
    *,
    edited_input: Any = None,
    model_id: str | None = None,
) -> AiChatSession:
    """Branch at a reply or safely retry its original persisted input."""
    if mode not in {"before", "after", "retry", "edit"}:
        raise RuntimeRequestError("Unsupported branch mode")
    if mode == "edit" and (
        not isinstance(edited_input, str)
        or not edited_input.strip()
        or len(edited_input) > 64000
    ):
        raise RuntimeRequestError("Input must contain 1 to 64000 characters")
    source = get_turn(turn_id)
    if source.session_id != thread.id:
        raise RuntimeRequestError("Branch boundary not found", 404)
    state = loads(source.state_json)
    if mode == "retry":
        calls = state.get("checkpoint", {}).get("calls", {}).values()
        if any(
            call.get("effect") not in {"none", "read"}
            and (
                call.get("attempts", 0) > 0
                or call.get("status") in {"in_progress", "completed"}
            )
            for call in calls
        ):
            raise RuntimeRequestError(
                "This turn changed BI resources or has an uncertain outcome. "
                "Fork chat to continue without repeating those changes.",
                409,
            )
    if mode in {"retry", "edit"}:
        from superset.ai_runtime import images, model_catalog
        from superset.views.ai.config_store import resolve_active_config

        config = model_catalog.resolve(model_id, resolve_active_config())
        images.references(
            state.get("attachment_ids", []),
            state.get("messages", []),
            vision=bool(config.get("vision")),
        )
        validate_context(state.get("context", []))
    branch = fork(thread, source.id, include_turn=mode == "after")
    if mode in {"retry", "edit"}:
        submit(
            str(branch.uuid),
            {
                "input": edited_input.strip()
                if mode == "edit"
                else state.get("input_text", ""),
                "context": state.get("context", []),
                "workflow_ids": state.get("workflow_ids", []),
                "idempotency_key": f"{mode}-{source.id}",
                "model_id": model_id,
                "attachment_ids": state.get("attachment_ids", []),
            },
        )
    return branch


def fork(
    thread: AiChatSession, turn_id: str, *, include_turn: bool = False
) -> AiChatSession:
    """Copy completed context at a turn boundary without executing operations."""
    target = (
        db.session.query(AiRuntimeTurn)
        .filter_by(id=turn_id, session_id=thread.id)
        .first()
    )
    if not target:
        raise RuntimeRequestError("Branch boundary not found", 404)
    if include_turn and target.status != "completed":
        raise RuntimeRequestError(
            "Only completed replies can be included in a branch", 409
        )
    if db.session.query(AiRuntimeTurn).filter_by(active_key=str(thread.uuid)).first():
        raise RuntimeRequestError("Stop the current turn before branching", 409)
    user_id, post_id = current_scope()
    branch = AiChatSession(
        title=thread.title,
        runtime_version=2,
        post_id=post_id,
        parent_uuid=str(thread.uuid),
        profile_id=thread.profile_id,
        created_by_fk=user_id,
        changed_by_fk=user_id,
    )
    db.session.add(branch)
    db.session.flush()
    eligible = (
        db.session.query(AiRuntimeTurn)
        .filter(
            AiRuntimeTurn.session_id == thread.id,
            AiRuntimeTurn.created_on <= target.created_on
            if include_turn
            else AiRuntimeTurn.created_on < target.created_on,
            AiRuntimeTurn.status == "completed",
        )
        .order_by(AiRuntimeTurn.created_on)
        .all()
    )
    turn_ids: dict[str, str] = {}
    artifact_ids: dict[str, dict[str, Any]] = {}
    for previous in eligible:
        checkpoint = AiRuntimeTurn(
            session_id=branch.id,
            user_id=user_id,
            post_id=post_id,
            idempotency_key=f"branch-context-{previous.id}",
            input_hash=previous.input_hash,
            status="completed",
            content=previous.content,
            state_json=previous.state_json,
            created_on=previous.created_on,
        )
        db.session.add(checkpoint)
        db.session.flush()
        turn_ids[previous.id] = checkpoint.id
        for item in (
            db.session.query(AiRuntimeItem).filter_by(turn_id=previous.id).all()
        ):
            if item.kind in {
                "tool",
                "reasoning_status",
                "reasoning_summary",
                "progress",
            }:
                db.session.add(
                    AiRuntimeItem(
                        turn_id=checkpoint.id,
                        kind=item.kind,
                        status=item.status,
                        payload_json=item.payload_json,
                        created_on=item.created_on,
                    )
                )
        for original in (
            db.session.query(AiRuntimeArtifact).filter_by(turn_id=previous.id).all()
        ):
            copied_artifact = AiRuntimeArtifact(
                turn_id=checkpoint.id,
                artifact_type=original.artifact_type,
                title=original.title,
                version=original.version,
                payload_json=original.payload_json,
                provenance_json=dumps(
                    {
                        **loads(original.provenance_json),
                        "source_artifact_id": original.id,
                        "source_thread_id": str(thread.uuid),
                    }
                ),
            )
            db.session.add(copied_artifact)
            db.session.flush()
            artifact_ids[original.id] = artifact_dict(copied_artifact)
    for message in thread.messages:
        extra = message.extra or {}
        original_turn_id = extra.get("runtime_turn_id")
        if original_turn_id in turn_ids:
            copy = AiChatMessage(
                session_id=branch.id,
                role=message.role,
                content=message.content,
                created_on=message.created_on,
            )
            copy.extra = {
                **extra,
                "branched": True,
                "runtime_turn_id": turn_ids[original_turn_id],
                "artifacts": [
                    artifact_ids[a["id"]]
                    for a in extra.get("artifacts", [])
                    if a.get("id") in artifact_ids
                ],
            }
            db.session.add(copy)
    db.session.commit()
    return branch

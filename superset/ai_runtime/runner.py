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
"""Worker leases, database checkpoints, and recovery around the agent engine."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from flask import current_app, g
from sqlalchemy import or_

from superset import security_manager
from superset.ai_runtime import artifact_memory, deliverables, notifications, store
from superset.extensions import celery_app, db
from superset.models.ai_chat import AiChatMessage
from superset.models.ai_runtime import (
    AiRuntimeArtifact,
    AiRuntimeItem,
    AiRuntimeOutbox,
    AiRuntimeTurn,
)

logger = logging.getLogger(__name__)
LEASE_SECONDS = 60


def artifact_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    """Capture permitted native chart configuration without changing MCP output."""
    payload = deepcopy(artifact.get("payload", artifact.get("data", {})))
    identifier = payload.get("slice_id", payload.get("id"))
    if not (
        artifact.get("type") == "chart"
        and artifact.get("provenance", {}).get("connection_id") == "focalbi"
        and isinstance(identifier, int)
    ):
        return payload
    from superset.models.slice import Slice

    resource = db.session.query(Slice).get(identifier)
    if resource and security_manager.can_access_chart(resource):
        if artifact.get("saved"):
            payload["form_data"] = resource.form_data
        elif isinstance(payload.get("form_data"), dict):
            payload["form_data"].setdefault(
                "datasource", f"{resource.datasource_id}__{resource.datasource_type}"
            )
    return payload


class LostLeaseError(RuntimeError):
    """A stale worker must stop before dispatching another external operation."""


def dispatch_pending() -> int:
    """Broker outages leave committed outbox rows available for later delivery."""
    count = 0
    rows = (
        db.session.query(AiRuntimeOutbox)
        .join(AiRuntimeTurn, AiRuntimeOutbox.turn_id == AiRuntimeTurn.id)
        .filter(
            AiRuntimeTurn.status == "queued",
            or_(
                AiRuntimeOutbox.status == "pending",
                (AiRuntimeOutbox.status == "dispatched")
                & (AiRuntimeOutbox.dispatched_on < store.now() - timedelta(seconds=30)),
            ),
        )
        .order_by(AiRuntimeOutbox.created_on)
        .limit(100)
        .all()
    )
    for row in rows:
        try:
            celery_app.send_task("ai_runtime.execute", args=[row.turn_id], queue="ai")
        except Exception:
            db.session.rollback()
            logger.warning("AI dispatch unavailable; committed outbox will retry")
            break
        # A crash after publish and before commit causes duplicate delivery; lease
        # acquisition and the operation ledger make that delivery safe.
        row.status = "dispatched"
        row.attempts += 1
        row.dispatched_on = store.now()
        db.session.commit()
        count += 1
    return count


def recover_stale() -> int:
    """Requeue abandoned turns; the engine reconciles uncertain operation records."""
    recovered = 0
    for turn in (
        db.session.query(AiRuntimeTurn)
        .filter(
            AiRuntimeTurn.status.in_(["running", "cancelling", "waiting_input"]),
            AiRuntimeTurn.lease_owner.isnot(None),
            AiRuntimeTurn.lease_expires < store.now(),
        )
        .with_for_update(skip_locked=True)
        .all()
    ):
        turn.lease_owner = None
        turn.lease_expires = None
        checkpoint = store.loads(turn.state_json, {}).get("checkpoint", {})
        uncertain = any(
            call.get("status") == "in_progress" and call.get("effect") != "read"
            for call in checkpoint.get("calls", {}).values()
        )
        if turn.status == "cancelling":
            turn.status = "needs_review" if uncertain else "cancelled"
            if not uncertain:
                turn.active_key = None
            store.append_event(
                turn,
                "status" if uncertain else "turn_completed",
                {"status": turn.status},
                commit=False,
            )
        else:
            if store.loads(turn.state_json).get("execution_engine") == "sdk_native":
                turn.content = checkpoint.get("content", "")
                store.append_event(
                    turn, "message_reset", {"content": turn.content}, commit=False
                )
            turn.status = "queued"
            db.session.add(AiRuntimeOutbox(turn_id=turn.id))
            store.append_event(
                turn,
                "status",
                {"status": "queued", "message": "Recovering interrupted execution"},
                commit=False,
            )
        for item in (
            db.session.query(AiRuntimeItem)
            .filter(
                AiRuntimeItem.turn_id == turn.id,
                AiRuntimeItem.status == "running",
                AiRuntimeItem.kind.in_(
                    ["tool", "reasoning_status", "reasoning_summary", "model_reasoning"]
                ),
            )
            .all()
        ):
            item.status = "cancelled" if turn.status == "cancelled" else "interrupted"
            item.payload_json = store.dumps(
                {
                    **store.loads(item.payload_json),
                    "interruption_reason": "cancelled"
                    if turn.status == "cancelled"
                    else "worker_lease_expired",
                }
            )
            store.append_event(
                turn,
                "activity_updated",
                {
                    "item": store.activity_item(turn, item),
                },
                item_id=item.id,
                commit=False,
            )
        recovered += 1
    db.session.commit()
    return recovered


def _bind_actor(turn: AiRuntimeTurn) -> str | None:
    """Rehydrate current permissions; captured credentials never stand in for them."""
    user = security_manager.get_user_by_id(turn.user_id)
    if (
        not user
        or not user.active
        or turn.post_id not in {p.id for p in security_manager.get_user_posts(user)}
    ):
        raise store.RuntimeRequestError(
            "Conversation permissions were revoked", 403, "permission_revoked"
        )
    g.user = user
    g.mcp_active_post_id = turn.post_id
    if not security_manager.can_access("can_chat", "AI"):
        raise store.RuntimeRequestError(
            "AI Chat permission was revoked", 403, "permission_revoked"
        )
    if current_app.config.get("MCP_AUTH_ENABLED", False):
        from superset.views.ai.mcp_jwt import mint_mcp_user_token

        return mint_mcp_user_token(user=user, active_post_id=turn.post_id)
    return None


def execute_turn(turn_id: str) -> None:  # noqa: C901 - explicit execution state machine
    """Acquire exactly one live worker, then run/resume persisted engine state."""
    owner = str(uuid4())
    claimed = (
        db.session.query(AiRuntimeTurn)
        .filter(
            AiRuntimeTurn.id == turn_id,
            AiRuntimeTurn.status == "queued",
            or_(
                AiRuntimeTurn.lease_owner.is_(None),
                AiRuntimeTurn.lease_expires < store.now(),
            ),
        )
        .update(
            {
                "status": "running",
                "lease_owner": owner,
                "lease_expires": store.now() + timedelta(seconds=LEASE_SECONDS),
            },
            synchronize_session=False,
        )
    )
    db.session.commit()
    if not claimed:
        return
    turn = db.session.query(AiRuntimeTurn).get(turn_id)
    turn.error_json = None
    db.session.commit()
    state = store.loads(turn.state_json)
    state.update(
        turn_id=turn.id,
        thread_id=turn.active_key,
        user_id=turn.user_id,
        post_id=turn.post_id,
    )
    deltas: list[str] = []
    last_delta_flush = time.monotonic()
    last_lease_renewal = time.monotonic()

    def live() -> AiRuntimeTurn:
        nonlocal last_lease_renewal
        db.session.expire(turn)
        db.session.refresh(turn)
        if turn.lease_owner != owner:
            raise LostLeaseError("AI worker lease was replaced")
        # Streaming callbacks also renew the lease if the timer task is delayed.
        if time.monotonic() - last_lease_renewal >= 10:
            turn.lease_expires = store.now() + timedelta(seconds=LEASE_SECONDS)
            db.session.commit()
            last_lease_renewal = time.monotonic()
        return turn

    def refresh_auth() -> str | None:
        live()
        return _bind_actor(turn)

    def cancelled() -> bool:
        return live().status in {"cancelling", "cancelled"}

    def checkpoint(cp: dict[str, Any]) -> None:
        flush_deltas()
        live()
        current = store.loads(turn.state_json)
        current["checkpoint"] = cp
        current["messages"] = cp.get("messages", current.get("messages", []))
        turn.state_json = store.dumps(current)
        turn.content = cp.get("content", turn.content)
        turn.lease_expires = store.now() + timedelta(seconds=LEASE_SECONDS)
        db.session.commit()

    def consume_inputs() -> list[dict[str, Any]]:
        live()
        rows = (
            db.session.query(AiRuntimeItem)
            .filter_by(turn_id=turn.id, kind="user_input", status="pending")
            .order_by(AiRuntimeItem.created_on)
            .all()
        )
        inputs = []
        for row in rows:
            value = store.loads(row.payload_json)
            if state.get("execution_engine") == "sdk_native":
                inputs.append({**value, "_native_input_id": row.id})
            else:
                inputs.append(value)
                row.status = "completed"
        db.session.commit()
        return inputs

    def ack_native_inputs(identifiers: list[str]) -> None:
        live()
        db.session.query(AiRuntimeItem).filter(
            AiRuntimeItem.turn_id == turn.id,
            AiRuntimeItem.kind == "user_input",
            AiRuntimeItem.id.in_(identifiers),
        ).update({"status": "completed"}, synchronize_session=False)
        db.session.commit()

    state["_ack_native_inputs"] = ack_native_inputs

    def flush_deltas() -> None:
        nonlocal last_delta_flush
        if not deltas:
            return
        live()
        text = "".join(deltas)
        deltas.clear()
        turn.content = (turn.content or "") + text
        turn.lease_expires = store.now() + timedelta(seconds=LEASE_SECONDS)
        store.append_event(turn, "message_delta", {"content": text})
        last_delta_flush = time.monotonic()

    def record_reasoning(kind: str, payload: dict[str, Any]) -> str | None:
        generation = str(payload.get("generation_id", "legacy"))
        external = f"{generation}:{payload.get('summary_id', kind)}"
        identifier = str(uuid5(NAMESPACE_URL, f"{turn.id}:activity:{external}"))
        row = db.session.query(AiRuntimeItem).get(identifier)
        if row is None:
            if payload.get("only_existing"):
                return None
            row = AiRuntimeItem(id=identifier, turn_id=turn.id, kind=kind)
            db.session.add(row)
        row.status = str(
            payload.get("status")
            or (
                "completed"
                if payload.get("completed")
                or (kind == "reasoning_summary" and "completed" not in payload)
                else "running"
            )
        )
        row.payload_json = store.dumps(
            {key: value for key, value in payload.items() if key != "only_existing"}
        )
        return row.id

    def emit(kind: str, payload: dict[str, Any]) -> None:  # noqa: C901 - durable event ledger
        if kind == "message_delta":
            deltas.append(str(payload.get("content", "")))
            if time.monotonic() - last_delta_flush >= 0.15:
                flush_deltas()
            return
        flush_deltas()
        live()
        item_id = None
        registration = None
        if kind == "message_reset":
            turn.content = str(payload.get("content", ""))
        if kind in {"tool_started", "tool_completed"}:
            external = str(payload.get("call_id", payload.get("id", "")))
            row = (
                db.session.query(AiRuntimeItem)
                .filter_by(turn_id=turn.id, kind="tool", external_id=external)
                .first()
            )
            if row is None:
                row = AiRuntimeItem(
                    id=str(uuid4()), turn_id=turn.id, kind="tool", external_id=external
                )
                db.session.add(row)
            row.status = (
                "running"
                if kind == "tool_started"
                else ("failed" if payload.get("isError") else "completed")
            )
            row.payload_json = store.dumps({**store.loads(row.payload_json), **payload})
            item_id = row.id
        elif kind in {"reasoning_status", "reasoning_summary", "model_reasoning"}:
            item_id = record_reasoning(kind, payload)
            if item_id is None:
                return
        elif kind == "artifact":
            artifact = payload.get("artifact", payload)
            identifier = str(
                uuid5(
                    NAMESPACE_URL,
                    f"{turn.id}:{artifact.get('id') or artifact.get('title')}",
                )
            )
            row = db.session.query(AiRuntimeArtifact).get(identifier)
            if row is None:
                payload_data = artifact_payload(artifact)
                if artifact.get("provenance", {}).get("connection_id") == "focalbi":
                    payload_data = artifact_memory.hydrate_preview(payload_data)
                if (
                    artifact.get("type") == "chart"
                    and artifact.get("provenance", {}).get("connection_id") == "focalbi"
                ):
                    existing = artifact_memory.find_preview(turn, payload_data)
                    if existing is not None:
                        turn.lease_expires = store.now() + timedelta(
                            seconds=LEASE_SECONDS
                        )
                        store.append_event(
                            turn, kind, {"artifact": store.artifact_dict(existing)}
                        )
                        return
                resource_id = payload_data.get("slice_id", payload_data.get("id"))
                version = artifact.get("version", 1)
                if resource_id is not None:
                    prior = (
                        db.session.query(AiRuntimeArtifact)
                        .join(
                            AiRuntimeTurn, AiRuntimeArtifact.turn_id == AiRuntimeTurn.id
                        )
                        .filter(
                            AiRuntimeTurn.session_id == turn.session_id,
                            AiRuntimeArtifact.artifact_type == artifact.get("type"),
                            AiRuntimeArtifact.turn_id != turn.id,
                        )
                        .all()
                    )
                    version = 1 + max(
                        (
                            item.version
                            for item in prior
                            if store.loads(item.payload_json).get(
                                "slice_id", store.loads(item.payload_json).get("id")
                            )
                            == resource_id
                        ),
                        default=0,
                    )
                row = AiRuntimeArtifact(
                    id=identifier,
                    turn_id=turn.id,
                    artifact_type=artifact.get("type", "source"),
                    title=str(artifact.get("title", "Result"))[:256],
                    version=version,
                    payload_json=store.dumps(
                        {
                            **payload_data,
                            "saved": bool(artifact.get("saved")),
                        }
                    ),
                    provenance_json=store.dumps(artifact.get("provenance", {})),
                )
                db.session.add(row)
            db.session.flush()
            payload = {"artifact": store.artifact_dict(row)}
            registration = deliverables.auto_present(turn, payload["artifact"])
        turn.lease_expires = store.now() + timedelta(seconds=LEASE_SECONDS)
        if item_id:
            row = db.session.query(AiRuntimeItem).get(item_id)
            store.append_event(turn, kind, payload, item_id=item_id, commit=False)
            store.append_event(
                turn,
                "activity_updated",
                {
                    "item": store.activity_item(turn, row),
                },
                item_id=item_id,
            )
            if kind == "tool_completed" and deliverables.removed_chart_keys(row):
                store.append_event(
                    turn, "deliverable", {"deliverables": deliverables.listing(turn)}
                )
        else:
            store.append_event(turn, kind, payload, commit=registration is None)
            if registration:
                store.append_event(turn, "deliverable", {"deliverable": registration})

    async def elicit(
        message: str, response_type: Any, params: Any, context: Any
    ) -> Any:
        """Bridge supported MCP form elicitation to a bounded durable UI request."""
        from fastmcp.client.elicitation import ElicitResult

        from superset.ai_runtime.policy import validate_arguments

        schema = getattr(params, "requestedSchema", None)
        # Authentication stays in the account-linking flow, never elicitation.
        if schema is None or any(
            secret in store.dumps(schema).lower()
            for secret in ("password", "access_token", "api_key", "client_secret")
        ):
            return ElicitResult(action="decline")
        pending = AiRuntimeItem(
            id=str(uuid4()),
            turn_id=turn.id,
            kind="request",
            status="pending",
            payload_json=store.dumps(
                {
                    "kind": "clarification",
                    "message": message,
                    "schema": schema,
                    "live_session": True,
                    "expires_at": (store.now() + timedelta(minutes=5)).isoformat()
                    + "Z",
                }
            ),
        )
        db.session.add(pending)
        turn.status = "waiting_input"
        store.append_event(
            turn,
            "request",
            {"request": {"id": pending.id, **store.loads(pending.payload_json)}},
        )
        for _ in range(600):
            await asyncio.sleep(0.5)
            if cancelled():
                return ElicitResult(action="cancel")
            db.session.refresh(pending)
            if pending.status == "completed":
                response = store.loads(pending.payload_json).get("response", {})
                answer = response.get("content")
                if answer is None:
                    try:
                        answer = store.loads(response.get("input", ""))
                    except (TypeError, ValueError):
                        return ElicitResult(action="decline")
                validate_arguments(schema, answer)
                turn.status = "running"
                db.session.commit()
                return ElicitResult(action="accept", content=answer)
        pending.status = "expired"
        turn.status = "running"
        store.append_event(
            turn,
            "status",
            {
                "status": "running",
                "message": "Tool question expired; operation was declined",
            },
        )
        return ElicitResult(action="decline")

    async def run() -> dict[str, Any]:  # noqa: C901 - scoped runtime callbacks
        from superset.ai_runtime.connections import resolve_connections
        from superset.ai_runtime.engine import run_turn
        from superset.ai_runtime.tool_access import authorize_tool, current_tool_allowed

        token = refresh_auth()
        state["_tool_filter"] = current_tool_allowed
        state["_authorize_tool"] = authorize_tool
        state["connections"] = resolve_connections(
            state.get("connection_ids", []),
            turn.user_id,
            turn.post_id,
            focal_config=state.get("config"),
        )

        async def timed_elicit(
            message: str, response_type: Any, params: Any, context: Any
        ) -> Any:
            started = time.monotonic()
            try:
                return await elicit(message, response_type, params, context)
            finally:
                state["_waiting_seconds"] = (
                    state.get("_waiting_seconds", 0) + time.monotonic() - started
                )

        state["_elicitation_handler"] = timed_elicit
        for connection in state["connections"]:
            connection.update(user_id=turn.user_id, post_id=turn.post_id)
            if connection.get("is_focal") and token:
                connection["bearer_token"] = token
            if not connection.get("is_focal"):
                connection_id = connection["id"]

                def credential_refresh(
                    selected: str = connection_id,
                    version: int = connection.get("version", 1),
                ) -> str | None:
                    refreshed = resolve_connections(
                        [selected], turn.user_id, turn.post_id
                    )[0]
                    if refreshed.get("version", 1) != version:
                        raise store.RuntimeRequestError(
                            "Connection changed during execution; start a new turn",
                            409,
                            "connection_changed",
                        )
                    return refreshed.get("bearer_token")

                connection["credential_refresh"] = credential_refresh

        def artifact_index() -> list[dict[str, Any]]:
            refresh_auth()
            return artifact_memory.index(turn)

        def read_artifact(identifier: str | None = None) -> dict[str, Any]:
            refresh_auth()
            return artifact_memory.read(turn, identifier)

        def present_deliverable(
            args: dict[str, Any], operation_id: str
        ) -> dict[str, Any]:
            refresh_auth()
            if cancelled():
                raise store.RuntimeRequestError("Turn is stopping", 409)
            value = deliverables.present(turn, args, operation_id)
            live()  # Revalidate lease before committing the presentation.
            projection = deliverables.listing(turn)
            current = next(
                (entry for entry in projection if entry["key"] == value["key"]), None
            )
            store.append_event(
                turn,
                "deliverable",
                {"deliverable": current} if current else {"deliverables": projection},
            )
            return value

        def artifact_refs(call_id: str | None = None) -> list[dict[str, Any]]:
            refresh_auth()
            return deliverables.references(turn, call_id)

        state["_present_deliverable"] = present_deliverable
        state["_artifact_refs"] = artifact_refs
        state["_artifact_index"] = artifact_index
        state["_read_artifact"] = read_artifact

        def read_record(call_id: str) -> dict[str, Any] | None:
            refresh_auth()
            source = (
                db.session.query(AiRuntimeTurn)
                .join(AiRuntimeItem, AiRuntimeItem.turn_id == AiRuntimeTurn.id)
                .filter(
                    AiRuntimeTurn.session_id == turn.session_id,
                    AiRuntimeTurn.user_id == turn.user_id,
                    AiRuntimeTurn.post_id == turn.post_id,
                    AiRuntimeItem.kind == "tool",
                    AiRuntimeItem.external_id == call_id,
                )
                .first()
            )
            return (
                store.loads(source.state_json)
                .get("checkpoint", {})
                .get("calls", {})
                .get(call_id)
                if source
                else None
            )

        state["_read_record"] = read_record
        state["_authorize_refs"] = store.validate_context
        state["_validate_preview"] = artifact_memory.validate_preview
        if state.get("execution_engine") == "sdk_native":
            from superset.ai_runtime.context import digest
            from superset.ai_runtime.native_session import (
                application_models,
                FocalSession,
            )

            state["_native_session"] = FocalSession(
                str(state["thread_id"]),
                database=db.session,
                models=application_models(),
                owner_id=turn.user_id,
                post_id=turn.post_id,
                turn_id=turn.id,
                binding=digest(
                    {
                        key: state["config"].get(key)
                        for key in (
                            "llmApiBaseUrl",
                            "llmModel",
                            "model_connection_id",
                            "model_revision",
                        )
                    }
                ),
                guard=refresh_auth,
                offset=int(state.get("checkpoint", {}).get("session_offset", 0)),
                allow_rebind=not bool(
                    state.get("checkpoint", {}).get("native_started")
                ),
            )
        validate_refs = state.get("context", [])
        store.validate_context(validate_refs)

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(10)
                live()
                turn.lease_expires = store.now() + timedelta(seconds=LEASE_SECONDS)
                db.session.commit()

        monitor = asyncio.create_task(heartbeat())
        try:
            return await run_turn(
                state,
                emit=emit,
                checkpoint=checkpoint,
                cancelled=cancelled,
                consume_inputs=consume_inputs,
                refresh_auth=refresh_auth,
            )
        finally:
            monitor.cancel()
            try:
                await monitor
            except asyncio.CancelledError:
                pass

    try:
        result = asyncio.run(run())
        flush_deltas()
        live()
        for artifact in result.get("artifacts", []):
            emit("artifact", artifact)
        final_state = store.loads(turn.state_json)
        final_state.update(
            messages=result.get("messages", final_state.get("messages", [])),
            checkpoint=result.get("checkpoint", final_state.get("checkpoint", {})),
        )
        final_state.pop("pending_response", None)
        final_state["pending_request"] = result.get("pending_request")
        turn.state_json = store.dumps(final_state)
        turn.content = result.get("content", turn.content) or ""
        turn.status = result["status"]
        if turn.status == "queued":
            db.session.add(AiRuntimeOutbox(turn_id=turn.id))
        request = result.get("pending_request")
        if request:
            pending = AiRuntimeItem(
                id=str(uuid4()), turn_id=turn.id, kind="request", status="pending"
            )
            pending.payload_json = store.dumps(
                {
                    **request,
                    "message": request.get("message")
                    or request.get("question", "Review the proposed action"),
                    "expires_at": (store.now() + timedelta(minutes=30)).isoformat()
                    + "Z",
                }
            )
            db.session.add(pending)
            store.append_event(
                turn,
                "request",
                {"request": {"id": pending.id, **store.loads(pending.payload_json)}},
                commit=False,
            )
        if turn.status in store.TERMINAL:
            turn.active_key = None
            existing = (
                db.session.query(AiRuntimeItem)
                .filter_by(turn_id=turn.id, kind="assistant_message")
                .first()
            )
            if not existing:
                artifacts = (
                    db.session.query(AiRuntimeArtifact).filter_by(turn_id=turn.id).all()
                )
                message = AiChatMessage(
                    session_id=turn.session_id, role="assistant", content=turn.content
                )
                message.extra = {
                    "runtime_turn_id": turn.id,
                    "artifacts": [store.artifact_dict(a) for a in artifacts],
                    "stopped": turn.status == "cancelled",
                }
                db.session.add(message)
                db.session.add(
                    AiRuntimeItem(
                        turn_id=turn.id,
                        kind="assistant_message",
                        payload_json=store.dumps({"content": turn.content}),
                    )
                )
        else:
            turn.active_key = state["thread_id"]
        turn.lease_owner, turn.lease_expires = None, None
        event = "turn_completed" if turn.status in store.TERMINAL else "status"
        store.append_event(turn, event, {"status": turn.status}, commit=False)
        db.session.commit()
        notifications.publish(turn.id)
    except LostLeaseError:
        db.session.rollback()
        logger.warning("AI stale worker stopped for turn %s", turn_id)
    except Exception as ex:
        db.session.rollback()
        live()
        from superset.ai_runtime.connections import ConnectionError

        def repair_message(error: BaseException) -> str | None:
            if (
                isinstance(error, ConnectionError)
                or getattr(error, "code", None) == "connection_auth"
            ):
                return str(error)
            return next(
                (
                    message
                    for child in getattr(error, "exceptions", [])
                    if (message := repair_message(child))
                ),
                None,
            )

        account_problem = repair_message(ex)
        if account_problem:
            # Account repair is an interaction, not a lost or restarted run.
            pending = AiRuntimeItem(
                id=str(uuid4()),
                turn_id=turn.id,
                kind="request",
                status="pending",
                payload_json=store.dumps(
                    {
                        "kind": "connection",
                        "message": (
                            "The shared AI service needs administrator attention. "
                            "Ask an administrator to repair its connection "
                            "in AI Connection, then resume this task."
                        ),
                        "expires_at": (store.now() + timedelta(minutes=30)).isoformat()
                        + "Z",
                    }
                ),
            )
            db.session.add(pending)
            current = store.loads(turn.state_json)
            current["pending_request"] = store.loads(pending.payload_json)
            turn.state_json = store.dumps(current)
            turn.status = "waiting_input"
            turn.lease_owner, turn.lease_expires = None, None
            store.append_event(
                turn,
                "request",
                {"request": {"id": pending.id, **store.loads(pending.payload_json)}},
            )
            return
        cp = store.loads(turn.state_json).get("checkpoint", {})
        uncertain = any(
            v.get("status") == "in_progress" and v.get("effect") != "read"
            for v in cp.get("calls", {}).values()
        )
        turn.status = "needs_review" if uncertain else "failed"
        if code := getattr(ex, "code", None):
            if code == "cancelled" and not uncertain:
                turn.status = "cancelled"
        accepted = store.loads(turn.state_json)
        if accepted.get("execution_engine") == "sdk_native" and not uncertain:
            from superset.ai_runtime.native_history import seal_terminal
            from superset.ai_runtime.native_session import application_models

            seal_terminal(db.session, application_models(), turn, cp)
        if not uncertain:
            turn.active_key = None
        turn.lease_owner, turn.lease_expires = None, None
        code = getattr(ex, "code", "execution_failed")
        # Upstream exceptions can embed tokens or query contents; only expose
        # deliberate runtime errors, and never log the exception body.
        safe = getattr(ex, "to_event", None)
        turn.error_json = store.dumps(
            safe()
            if callable(safe)
            else {
                "code": code,
                "message": (
                    "Execution failed. Inspect connection status "
                    "or retry in a new branch."
                ),
            }
        )
        store.append_event(
            turn,
            "turn_failed",
            {"status": turn.status, "error": store.loads(turn.error_json)},
            commit=False,
        )
        db.session.commit()
        notifications.publish(turn.id)
        logger.warning(
            "AI turn %s ended with %s (%s); frames=%s",
            turn_id,
            code,
            type(ex).__name__,
            [
                (frame.filename, frame.lineno, frame.name)
                for frame in traceback.extract_tb(ex.__traceback__)
            ],
        )

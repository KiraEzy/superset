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
"""Public turn APIs; the browser submits intent rather than trusted history."""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Iterator

from flask import jsonify, request, Response, stream_with_context
from flask_appbuilder.api import BaseApi, expose, protect, safe

from superset import security_manager
from superset.ai_runtime import images, model_catalog, notifications, settings, store
from superset.extensions import db
from superset.models.ai_chat import AiChatSession
from superset.models.ai_runtime import AiRuntimeEvent


def runtime_errors(function: Callable[..., Any]) -> Callable[..., Any]:
    """Keep validation failures typed and never leak provider/credential details."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except store.RuntimeRequestError as ex:
            db.session.rollback()
            return jsonify({"message": str(ex), "code": ex.code}), ex.status
        except ValueError:
            db.session.rollback()
            return jsonify(
                {
                    "message": "Invalid request or unavailable connection",
                    "code": "invalid_request",
                }
            ), 400

    return wrapped


def body() -> dict[str, Any]:
    """Require an object request body instead of accepting arbitrary JSON types."""
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise store.RuntimeRequestError("A JSON object is required")
    return value


class AIRuntimeRestApi(BaseApi):
    """Durable execution operations using the existing AI chat permission."""

    resource_name = "ai"
    class_permission_name = "AI"
    allow_browser_login = True
    openapi_spec_tag = "AI"
    method_permission_name = {
        name: "chat"
        for name in (
            "metadata",
            "submit",
            "get",
            "events",
            "cancel",
            "input",
            "fork",
            "upload_image",
            "preview_image",
            "remove_image",
        )
    }

    @expose("/runtime/", methods=("GET",))
    @protect()
    @safe
    @runtime_errors
    def metadata(self) -> Response:
        """Expose capabilities without returning provider or account credentials."""
        if not settings.enabled():
            return jsonify({"enabled": False, "workflows": []})
        _, post_id = store.current_scope()
        from superset.ai_runtime.workflows import workflow_catalog

        post = next(p for p in security_manager.get_user_posts() if p.id == post_id)
        return jsonify(
            {
                "enabled": True,
                "post": {"id": post_id, "name": post.name},
                "workflows": workflow_catalog(),
                "limits": settings.limits(),
                "models": model_catalog.catalogue()["models"],
                "image_limits": images.limits(),
            }
        )

    @expose("/threads/<thread_id>/turns", methods=("POST",))
    @protect()
    @safe
    @runtime_errors
    def submit(self, thread_id: str) -> Response:
        """Accept input transactionally before scheduling any execution."""
        turn = store.submit(thread_id, body())
        # Broker availability does not determine acceptance: the durable outbox
        # dispatcher owns eventual delivery and avoids blocking the web request.
        return jsonify({"result": store.snapshot(turn)}), 202

    @expose("/turns/<turn_id>", methods=("GET",))
    @protect()
    @safe
    @runtime_errors
    def get(self, turn_id: str) -> Response:
        """Return authoritative resumable state."""
        return jsonify({"result": store.snapshot(store.get_turn(turn_id))})

    @expose("/turns/<turn_id>/cancel", methods=("POST",))
    @protect()
    @safe
    @runtime_errors
    def cancel(self, turn_id: str) -> Response:
        """Request cancellation independently of any stream connection."""
        return jsonify(
            {"result": store.snapshot(store.cancel(store.get_turn(turn_id, lock=True)))}
        )

    @expose("/turns/<turn_id>/input", methods=("POST",))
    @protect()
    @safe
    @runtime_errors
    def input(self, turn_id: str) -> Response:
        """Respond to one pending interaction or steer at a safe boundary."""
        return jsonify(
            {
                "result": store.snapshot(
                    store.input_turn(store.get_turn(turn_id, lock=True), body())
                )
            }
        )

    @expose("/threads/<thread_id>/fork", methods=("POST",))
    @protect()
    @safe
    @runtime_errors
    def fork(self, thread_id: str) -> Response:
        """Branch conversation context without undoing saved BI resources."""
        from superset.ai_chat.api import session_to_dict

        data = body()
        branch = store.branch_reply(
            store.get_thread(thread_id, lock=True),
            data.get("turn_id", ""),
            data.get("mode", "before"),
            edited_input=data.get("input"),
            model_id=data.get("model_id"),
        )
        return jsonify({"result": session_to_dict(branch, include_messages=True)}), 201

    @expose("/turns/<turn_id>/events", methods=("GET",))
    @protect()
    @safe
    @runtime_errors
    def events(self, turn_id: str) -> Response:  # noqa: C901 - durable replay loop
        """Replay persisted events; disconnecting never cancels the worker."""
        turn = store.get_turn(turn_id)
        try:
            cursor = max(
                0,
                int(
                    request.headers.get("Last-Event-ID", request.args.get("after", "0"))
                ),
            )
        except ValueError as ex:
            raise store.RuntimeRequestError("Invalid event cursor") from ex
        if cursor > turn.next_sequence:
            raise store.RuntimeRequestError(
                "Event cursor is ahead of this turn", 409, "invalid_cursor"
            )
        thread = db.session.query(AiChatSession).get(turn.session_id)
        thread_id = str(thread.uuid)

        def replay(channel: Any) -> Iterator[str]:
            nonlocal cursor
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                # Close read transactions between polls so workers are not blocked
                # and permission revocations apply on the next delivery cycle.
                db.session.rollback()
                try:
                    current = store.get_turn(turn_id)
                except store.RuntimeRequestError:
                    return
                rows = (
                    db.session.query(AiRuntimeEvent)
                    .filter(
                        AiRuntimeEvent.turn_id == turn_id,
                        AiRuntimeEvent.sequence > cursor,
                    )
                    .order_by(AiRuntimeEvent.sequence)
                    .limit(200)
                    .all()
                )
                for row in rows:
                    payload = store.loads(row.payload_json)
                    if row.event_type in {"turn_completed", "turn_failed"}:
                        payload = {**payload, "turn": store.snapshot(current)}
                    event = {
                        "schema_version": 1,
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "item_id": row.item_id,
                        "sequence": row.sequence,
                        "timestamp": row.created_on.isoformat() + "Z",
                        "type": row.event_type,
                        "payload": payload,
                    }
                    cursor = row.sequence
                    yield f"id: {cursor}\ndata: {store.dumps(event)}\n\n"
                if current.status in store.TERMINAL and cursor >= current.next_sequence:
                    return
                if not rows:
                    yield ": heartbeat\n\n"
                    notifications.wait(channel)

        def generate() -> Iterator[str]:
            with notifications.subscription(turn_id) as channel:
                yield from replay(channel)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @expose("/images/", methods=("POST",))
    @protect()
    @safe
    @runtime_errors
    def upload_image(self) -> Response:
        """Validate and privately store an image draft."""

        if not settings.enabled():
            raise store.RuntimeRequestError("Image uploads are disabled", 503)
        if (
            request.content_length
            and request.content_length > images.limits()["bytes"] + 65536
        ):
            raise store.RuntimeRequestError("Image exceeds the upload size limit", 413)
        file = request.files.get("file")
        if not file:
            raise store.RuntimeRequestError("An image is required")
        return jsonify({"result": images.upload(file)}), 201

    @expose("/images/<image_id>", methods=("GET",))
    @protect()
    @safe
    @runtime_errors
    def preview_image(self, image_id: str) -> Response:
        """Serve an authorized preview without public caching."""
        import base64

        row = images.get(image_id)
        return Response(
            base64.b64decode(row.data),
            mimetype=row.mime,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'",
            },
        )

    @expose("/images/<image_id>", methods=("DELETE",))
    @protect()
    @safe
    @runtime_errors
    def remove_image(self, image_id: str) -> Response:
        """Delete only unbound draft uploads."""

        row = images.get(image_id)
        if row.bound:
            raise store.RuntimeRequestError(
                "This image is retained in conversation history", 409
            )
        db.session.delete(row)
        db.session.commit()
        return jsonify({"result": True})

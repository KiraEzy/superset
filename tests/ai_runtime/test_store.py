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
"""Real SQLite ledger checks without touching the installed metadata database."""

from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from flask import Flask, g


@pytest.fixture(scope="module")
def test_app():
    from superset.app import SupersetApp
    from superset.initialization import SupersetAppInitializer
    from superset.extensions import appbuilder

    app = SupersetApp(__name__)
    app.config.from_object("superset.config")
    app.config.update(
        SECRET_KEY="isolated-test-key-only",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        AI_CHAT_RUNTIME_ENABLED=True,
        TESTING=True,
        MCP_AUTH_ENABLED=False,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        CACHE_CONFIG={},
        DATA_CACHE_CONFIG={},
    )
    appbuilder.baseviews = []
    SupersetAppInitializer(app).init_app()
    return app


@pytest.fixture
def ledger(monkeypatch, test_app):
    from superset.extensions import db

    app = test_app
    with app.test_request_context():
        from flask_appbuilder.security.sqla.models import User
        from superset.ai_runtime import connections, runner, store
        from superset.models.ai_chat import (
            AiChatSession,
            AiChatMessage,
            AiConnectionConfig,
        )
        from superset.models.ai_runtime import (
            AiRuntimeTurn,
            AiRuntimeItem,
            AiRuntimeEvent,
            AiRuntimeArtifact,
            AiRuntimeOutbox,
        )

        from superset.models.ai_model_catalog import (
            AiModelConnection,
            AiModel,
            AiChatImage,
            AiModelVerification,
        )

        tables = [
            AiConnectionConfig.__table__,
            AiModelConnection.__table__,
            AiModel.__table__,
            AiChatImage.__table__,
            AiModelVerification.__table__,
            User.__table__,
            AiChatSession.__table__,
            AiChatMessage.__table__,
            AiRuntimeTurn.__table__,
            AiRuntimeItem.__table__,
            AiRuntimeEvent.__table__,
            AiRuntimeArtifact.__table__,
            AiRuntimeOutbox.__table__,
        ]
        AiChatSession.metadata.create_all(db.engine, tables=tables)
        user = User(
            id=1,
            username="ledger-user",
            first_name="Test",
            last_name="User",
            email="test@example.invalid",
            active=True,
        )
        db.session.add(user)
        db.session.commit()
        from superset.ai_runtime.native_session import application_models

        sdk_rows = application_models()
        sdk_rows[0].metadata.create_all(db.engine)
        scope = {"post": 11}
        g.user = user
        manager = SimpleNamespace(
            get_active_post_id=lambda: scope["post"],
            get_user_posts=lambda user=None: [
                SimpleNamespace(id=11),
                SimpleNamespace(id=12),
            ],
            can_access=lambda *args: True,
            get_user_by_id=lambda identifier: db.session.query(User).get(identifier),
        )
        manager.can_access_chart = manager.can_access
        manager.can_access_dashboard = manager.can_access
        manager.can_access_datasource = manager.can_access
        monkeypatch.setattr(store, "security_manager", manager)
        monkeypatch.setattr(runner, "security_manager", manager)
        monkeypatch.setattr(
            connections, "resolve_connections", lambda *args, **kwargs: []
        )
        monkeypatch.setattr(connections, "validate_selection", lambda *args: None)
        from superset.views.ai import config_store

        monkeypatch.setattr(
            config_store,
            "resolve_active_config",
            lambda: {
                "llmProvider": "custom",
                "llmApiBaseUrl": "https://example.invalid/v1",
                "llmApiKey": "secret-never-public",
                "llmModel": "test-model",
                "mcpEnabled": False,
            },
        )
        thread = AiChatSession(
            title="Test",
            runtime_version=2,
            post_id=11,
            created_by_fk=1,
            changed_by_fk=1,
        )
        db.session.add(thread)
        db.session.commit()
        db.session.add(
            sdk_rows[0](
                id=str(thread.uuid), owner_id=1, post_id=11, binding="test", revision=0
            )
        )
        db.session.commit()
        yield SimpleNamespace(
            db=db,
            store=store,
            runner=runner,
            thread=thread,
            scope=scope,
            Turn=AiRuntimeTurn,
            Item=AiRuntimeItem,
            Event=AiRuntimeEvent,
            Artifact=AiRuntimeArtifact,
            Outbox=AiRuntimeOutbox,
        )
        db.session.remove()
        sdk_rows[0].metadata.drop_all(db.engine)
        AiChatSession.metadata.drop_all(db.engine, tables=list(reversed(tables)))


def payload(key="submit-1", text="Explain the metric"):
    return {
        "input": text,
        "idempotency_key": key,
        "connection_ids": [],
        "workflow_ids": [],
        "context": [],
    }


def test_submission_idempotency_outbox_and_secret_boundary(ledger):
    l = ledger
    first = l.store.submit(str(l.thread.uuid), payload())
    repeated = l.store.submit(str(l.thread.uuid), payload())
    assert first.id == repeated.id
    assert l.db.session.query(l.Turn).count() == 1
    assert l.db.session.query(l.Outbox).count() == 1
    assert "secret-never-public" not in l.store.dumps(l.store.snapshot(first))
    with pytest.raises(l.store.RuntimeRequestError, match="different input"):
        l.store.submit(str(l.thread.uuid), payload(text="Different"))
    with pytest.raises(l.store.RuntimeRequestError, match="active turn"):
        l.store.submit(str(l.thread.uuid), payload("submit-2"))


def test_post_and_user_isolation(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    l.scope["post"] = 12
    with pytest.raises(l.store.RuntimeRequestError, match="not found"):
        l.store.get_turn(turn.id)
    with pytest.raises(l.store.RuntimeRequestError, match="not found"):
        l.store.get_thread(str(l.thread.uuid))
    l.scope["post"] = 11
    g.user = SimpleNamespace(id=999, is_anonymous=False)
    with pytest.raises(l.store.RuntimeRequestError, match="not found"):
        l.store.get_turn(turn.id)


def test_approval_response_is_scoped_idempotent_and_expires(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    turn.status = "waiting_approval"
    state = l.store.loads(turn.state_json)
    state["checkpoint"] = {"pending_request": {"fingerprint": "exact-args-hash"}}
    turn.state_json = l.store.dumps(state)
    pending = l.Item(
        id=str(uuid4()),
        turn_id=turn.id,
        kind="request",
        status="pending",
        payload_json=l.store.dumps(
            {
                "kind": "approval",
                "fingerprint": "exact-args-hash",
                "expires_at": (l.store.now() + timedelta(minutes=1)).isoformat() + "Z",
            }
        ),
    )
    l.db.session.add(pending)
    l.db.session.commit()
    response = {
        "expected_turn_id": turn.id,
        "idempotency_key": "answer-1",
        "request_id": pending.id,
        "response": {"decision": "accept"},
    }
    l.store.input_turn(turn, response)
    l.store.input_turn(turn, response)
    assert l.store.loads(turn.state_json)["approved_scopes"] == ["exact-args-hash"]
    assert l.db.session.query(l.Item).filter_by(kind="user_input").count() == 1
    assert l.db.session.query(l.Outbox).count() == 2
    with pytest.raises(l.store.RuntimeRequestError, match="conflict"):
        l.store.input_turn(turn, {**response, "response": {"decision": "decline"}})


def test_cancel_queued_turn_and_replay_sequence(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    l.store.cancel(turn)
    l.store.cancel(turn)
    assert turn.status == "cancelled"
    assert turn.active_key is None
    events = (
        l.db.session.query(l.Event)
        .filter_by(turn_id=turn.id)
        .order_by(l.Event.sequence)
        .all()
    )
    assert [e.sequence for e in events] == [1, 2]
    assert events[-1].event_type == "turn_completed"
    assert l.store.submit(str(l.thread.uuid), payload("new-after-cancel")).id != turn.id


def test_durable_runner_persists_completion_and_deduplicates_worker(
    ledger, monkeypatch
):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    from superset.ai_runtime import engine

    calls = []

    async def fake_run(state, **callbacks):
        calls.append(state["turn_id"])
        callbacks["checkpoint"](
            {
                "messages": [{"role": "user", "content": state["input_text"]}],
                "calls": {},
            }
        )
        callbacks["emit"]("message_delta", {"content": "Verified answer"})
        return {
            "status": "completed",
            "content": "Verified answer",
            "messages": [{"role": "assistant", "content": "Verified answer"}],
            "checkpoint": {"calls": {}},
        }

    monkeypatch.setattr(engine, "run_turn", fake_run)
    l.runner.execute_turn(turn.id)
    l.runner.execute_turn(turn.id)
    l.db.session.refresh(turn)
    assert calls == [turn.id]
    assert turn.status == "completed" and turn.content == "Verified answer"
    assert turn.active_key is None
    public = l.store.snapshot(turn)
    assert public["items"][-1]["kind"] == "assistant_message"
    assert public["last_sequence"] >= 3


def test_stale_worker_recovery_preserves_uncertain_write_checkpoint(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    turn.status = "running"
    turn.lease_owner = "abandoned"
    turn.lease_expires = l.store.now() - timedelta(minutes=2)
    state = l.store.loads(turn.state_json)
    state["checkpoint"] = {
        "calls": {
            "write-1": {"id": "write-1", "effect": "write", "status": "in_progress"}
        }
    }
    turn.state_json = l.store.dumps(state)
    l.db.session.commit()
    assert l.runner.recover_stale() == 1
    assert turn.status == "queued" and turn.lease_owner is None
    assert (
        l.store.loads(turn.state_json)["checkpoint"]["calls"]["write-1"]["status"]
        == "in_progress"
    )


def test_cancelled_stale_write_requires_review(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    turn.status, turn.lease_owner = "cancelling", "abandoned"
    turn.lease_expires = l.store.now() - timedelta(minutes=2)
    state = l.store.loads(turn.state_json)
    state["checkpoint"] = {
        "calls": {"write": {"status": "in_progress", "effect": "write"}}
    }
    turn.state_json = l.store.dumps(state)
    l.db.session.commit()
    l.runner.recover_stale()
    assert turn.status == "needs_review"
    assert turn.active_key == str(l.thread.uuid)


def test_partial_model_output_does_not_regenerate_after_worker_loss(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    turn.status, turn.lease_owner = "running", "abandoned"
    turn.lease_expires = l.store.now() - timedelta(minutes=2)
    turn.content = "Already displayed partial answer"
    l.db.session.commit()
    l.runner.recover_stale()
    assert turn.status == "queued"
    assert turn.content == ""
    assert turn.active_key == str(l.thread.uuid)


def test_dispatched_but_lost_queue_message_is_republished(ledger, monkeypatch):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    outbox = l.db.session.query(l.Outbox).filter_by(turn_id=turn.id).one()
    outbox.status, outbox.dispatched_on = (
        "dispatched",
        l.store.now() - timedelta(minutes=2),
    )
    l.db.session.commit()
    published = []
    monkeypatch.setattr(
        l.runner.celery_app,
        "send_task",
        lambda *args, **kwargs: published.append((args, kwargs)),
    )
    assert l.runner.dispatch_pending() == 1
    assert published[0][1]["args"] == [turn.id]
    assert l.runner.dispatch_pending() == 0


def test_expired_connection_preserves_turn_for_relink(ledger, monkeypatch):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    from superset.ai_runtime import connections

    def expired(*args, **kwargs):
        raise connections.ConnectionError("Account expired; reconnect your account")

    monkeypatch.setattr(connections, "resolve_connections", expired)
    l.runner.execute_turn(turn.id)
    l.db.session.refresh(turn)
    assert turn.status == "waiting_input"
    assert turn.active_key == str(l.thread.uuid)
    request = l.store.snapshot(turn)["pending_requests"][0]
    assert request["kind"] == "connection"
    assert "administrator" in request["message"]
    assert "reconnect your account" not in request["message"]
    l.store.input_turn(
        turn,
        {
            "expected_turn_id": turn.id,
            "idempotency_key": "relinked",
            "request_id": request["id"],
            "response": {"input": "relinked"},
        },
    )
    assert turn.status == "queued"
    assert l.store.get_turn(turn.id).id == turn.id


def test_rollback_disables_new_inputs_without_hiding_accepted_turns(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    from flask import current_app

    current_app.config["AI_CHAT_RUNTIME_ENABLED"] = False
    try:
        with pytest.raises(l.store.RuntimeRequestError, match="disabled"):
            l.store.submit(str(l.thread.uuid), payload("after-rollback"))
        assert l.store.get_turn(turn.id).id == turn.id
        assert l.store.snapshot(turn)["status"] == "queued"
    finally:
        current_app.config["AI_CHAT_RUNTIME_ENABLED"] = True


def test_fork_copies_prior_evidence_and_artifact_provenance(ledger):
    l = ledger
    first = l.store.submit(str(l.thread.uuid), payload())
    first.status, first.active_key = "completed", None
    state = l.store.loads(first.state_json)
    state["messages"] = [
        {"role": "user", "content": "Explain the metric"},
        {"role": "assistant", "content": "Saved chart 55"},
    ]
    first.state_json = l.store.dumps(state)
    original = l.Artifact(
        turn_id=first.id,
        artifact_type="chart",
        title="Chart",
        payload_json=l.store.dumps({"slice_id": 55, "saved": True}),
        provenance_json="{}",
    )
    l.db.session.add(original)
    l.db.session.commit()
    target = l.store.submit(str(l.thread.uuid), payload("second-turn", "Change chart"))
    l.store.cancel(target)
    branch = l.store.fork(l.thread, target.id)
    assert str(branch.uuid) != str(l.thread.uuid)
    assert branch.parent_uuid == str(l.thread.uuid) and branch.post_id == 11
    copies = l.db.session.query(l.Artifact).filter(l.Artifact.id != original.id).all()
    assert len(copies) == 1
    assert l.store.loads(copies[0].provenance_json)["source_artifact_id"] == original.id
    assert l.store.loads(copies[0].payload_json)["slice_id"] == 55


def test_native_artifact_snapshot_preserves_preview_and_source_evidence(
    ledger, monkeypatch
):
    l = ledger
    resource = SimpleNamespace(
        datasource_id=8,
        datasource_type="table",
        form_data={
            "datasource": "8__table",
            "time_grain_sqla": "P1M",
            "adhoc_filters": [{"col": "region", "val": "East"}],
        },
    )
    monkeypatch.setattr(
        l.db.session,
        "query",
        lambda *args: SimpleNamespace(get=lambda identifier: resource),
    )
    original = {
        "type": "chart",
        "saved": False,
        "provenance": {"connection_id": "focalbi"},
        "payload": {"slice_id": 55, "form_data": {"time_grain_sqla": "P3M"}},
    }
    preview = l.runner.artifact_payload(original)
    assert preview["form_data"] == {"datasource": "8__table", "time_grain_sqla": "P3M"}
    assert "datasource" not in original["payload"]["form_data"]
    saved = l.runner.artifact_payload({**original, "saved": True})
    assert saved["form_data"]["time_grain_sqla"] == "P1M"
    assert saved["form_data"]["adhoc_filters"] == resource.form_data["adhoc_filters"]


def test_client_cannot_override_global_model_or_connections(ledger):
    l = ledger
    for override in (
        {"connection_ids": ["external"]},
        {"profile_id": "personal"},
        {"adapter": "responses"},
    ):
        with pytest.raises(l.store.RuntimeRequestError):
            l.store.submit(str(l.thread.uuid), {**payload(), **override})
    assert l.db.session.query(l.Turn).count() == 0
    data = {"input": "Explain the metric", "idempotency_key": "global"}
    turn = l.store.submit(str(l.thread.uuid), data)
    state = l.store.loads(turn.state_json)
    assert state["connection_ids"] == []
    assert state["config"]["llmModel"] == "test-model"


def test_public_metadata_has_no_connection_configuration(ledger, monkeypatch):
    import inspect
    from superset.ai_runtime import api

    monkeypatch.setattr(
        api,
        "security_manager",
        SimpleNamespace(
            get_user_posts=lambda: [SimpleNamespace(id=11, name="Test post")]
        ),
    )
    result = inspect.unwrap(api.AIRuntimeRestApi.metadata)(
        api.AIRuntimeRestApi.__new__(api.AIRuntimeRestApi)
    ).get_json()
    assert set(result) == {
        "enabled",
        "post",
        "workflows",
        "limits",
        "models",
        "image_limits",
    }
    assert "secret" not in str(result)


def test_global_model_and_mcp_apply_to_different_users_without_client_configuration(
    ledger, monkeypatch
):
    from flask_appbuilder.security.sqla.models import User
    from superset.models.ai_chat import AiChatSession
    from superset.views.ai import config_store

    config = {
        **config_store.resolve_active_config(),
        "mcpEnabled": True,
        "mcpServerUrl": "https://bi.example/mcp",
    }
    monkeypatch.setattr(config_store, "resolve_active_config", lambda: config)
    first = ledger.store.submit(
        str(ledger.thread.uuid),
        {"input": "Check health", "idempotency_key": "first-global"},
    )
    second_user = User(
        id=2,
        username="second-user",
        first_name="Second",
        last_name="User",
        email="second@example.invalid",
        active=True,
    )
    ledger.db.session.add(second_user)
    thread = AiChatSession(
        title="Second user",
        runtime_version=2,
        post_id=11,
        created_by_fk=2,
        changed_by_fk=2,
    )
    ledger.db.session.add(thread)
    ledger.db.session.commit()
    g.user = second_user
    second = ledger.store.submit(
        str(thread.uuid), {"input": "Check health", "idempotency_key": "second-global"}
    )
    for turn in (first, second):
        state = ledger.store.loads(turn.state_json)
        assert state["connection_ids"] == ["focalbi"]
        assert state["config"]["llmModel"] == "test-model"
        assert state["config"]["llmApiBaseUrl"] == "https://example.invalid/v1"
        assert "secret-never-public" not in ledger.store.dumps(
            ledger.store.snapshot(turn)
        )
    assert first.user_id != second.user_id


def test_settings_api_denies_non_admin_before_reading_configuration(
    ledger, monkeypatch
):
    import inspect
    from superset.views.ai import config_api, config_store

    monkeypatch.setattr(
        config_api, "security_manager", SimpleNamespace(is_admin=lambda: False)
    )
    monkeypatch.setattr(
        config_store,
        "masked_state",
        lambda: pytest.fail("Configuration must not be read"),
    )
    api = config_api.AIConnectionRestApi.__new__(config_api.AIConnectionRestApi)
    for method in (api.get_config, api.access_options, api.save_config):
        response, status = inspect.unwrap(method.__func__)(api)
        assert status == 403
        assert "required" in response.get_json()["message"]


def test_masked_model_test_key_is_bound_to_saved_provider_destination(
    ledger, monkeypatch
):
    from superset.constants import PASSWORD_MASK
    from superset.views.ai import config_store

    monkeypatch.setattr(
        config_store,
        "load_stored_state",
        lambda: {
            "llmProvider": "custom",
            "providerSettings": {
                "custom": {
                    "llmApiBaseUrl": "https://provider.example/v1",
                    "llmApiKey": "private-key",
                    "llmModel": "model",
                }
            },
        },
    )
    data = {
        "llmApiKey": PASSWORD_MASK,
        "llmApiBaseUrl": "https://provider.example/v1",
        "llmProvider": "custom",
    }
    assert config_store.resolve_test_key(data) == "private-key"
    with pytest.raises(ValueError, match="different provider endpoint"):
        config_store.resolve_test_key(
            {**data, "llmApiBaseUrl": "https://other.example/v1"}
        )


def test_older_settings_client_preserves_tool_restrictions_and_masked_secrets(
    ledger, monkeypatch
):
    from unittest.mock import MagicMock
    from superset.constants import PASSWORD_MASK
    from superset.views.ai import config_store

    existing = {
        "llmProvider": "custom",
        "providerSettings": {
            "custom": {
                "llmApiBaseUrl": "https://provider.example/v1",
                "llmModel": "model",
                "llmApiKey": "private-key",
            }
        },
        "mcpToolAccess": {"roles": {"Alpha": ["health_check"]}, "users": {}},
        "mcpBearerToken": "private-mcp-token",
    }
    monkeypatch.setattr(config_store, "load_stored_state", lambda: existing)
    database = MagicMock()
    monkeypatch.setattr(config_store, "db", database)
    incoming = {key: value for key, value in existing.items() if key != "mcpToolAccess"}
    incoming["providerSettings"] = {
        "custom": {**existing["providerSettings"]["custom"], "llmApiKey": PASSWORD_MASK}
    }
    incoming["mcpBearerToken"] = PASSWORD_MASK
    saved = config_store.save_state(incoming)
    assert saved["mcpToolAccess"] == existing["mcpToolAccess"]
    assert saved["providerSettings"]["custom"]["llmApiKey"] == "private-key"
    assert saved["mcpBearerToken"] == "private-mcp-token"


def test_chat_pins_sort_before_pagination_and_preserve_title(ledger):
    from datetime import datetime
    from superset.ai_chat.api import AiChatSessionInterface, session_to_dict
    from superset.ai_chat.schemas import AiChatSessionPutSchema
    from superset.commands.ai_chat.update import UpdateAiChatSessionCommand
    from superset.models.ai_chat import AiChatSession

    thread = ledger.thread
    thread.changed_on = datetime(2020, 1, 1)
    newer = AiChatSession(
        title="Recent",
        runtime_version=2,
        post_id=11,
        created_by_fk=1,
        changed_on=datetime(2030, 1, 1),
    )
    ledger.db.session.add(newer)
    ledger.db.session.commit()
    data = AiChatSessionPutSchema().load({"is_pinned": True})
    UpdateAiChatSessionCommand(thread.uuid, data).run()
    assert thread.title == "Test"
    assert session_to_dict(thread)["is_pinned"] is True
    interface = AiChatSessionInterface(AiChatSession)
    query = ledger.db.session.query(AiChatSession)
    assert (
        interface.apply_order_by(query, "changed_on", "desc").limit(1).one().id
        == thread.id
    )
    UpdateAiChatSessionCommand(thread.uuid, {"title": "Renamed"}).run()
    assert thread.is_pinned is True
    UpdateAiChatSessionCommand(thread.uuid, {"is_pinned": False}).run()
    assert thread.title == "Renamed"
    ledger.scope["post"] = 12
    from superset.daos.ai_chat import AiChatSessionDAO

    assert AiChatSessionDAO.find_by_uuid(thread.uuid) is None


def test_reply_fork_includes_selected_reply_and_remaps_branch_boundaries(ledger):
    from superset.models.ai_chat import AiChatMessage

    l = ledger
    source = l.store.submit(str(l.thread.uuid), payload())
    source.status, source.active_key, source.content = (
        "completed",
        None,
        "Evidence-based answer",
    )
    state = l.store.loads(source.state_json)
    state["messages"] = [
        {"role": "user", "content": "Explain the metric"},
        {"role": "assistant", "content": source.content},
    ]
    source.state_json = l.store.dumps(state)
    reply = AiChatMessage(
        session_id=l.thread.id, role="assistant", content=source.content
    )
    reply.extra = {"runtime_turn_id": source.id}
    l.db.session.add(reply)
    l.db.session.commit()
    branch = l.store.branch_reply(l.thread, source.id, "after")
    l.db.session.refresh(branch)
    copied = next(m for m in branch.messages if m.role == "assistant")
    copied_turn = l.db.session.query(l.Turn).filter_by(session_id=branch.id).one()
    assert copied.extra["runtime_turn_id"] == copied_turn.id != source.id
    assert l.db.session.query(l.Outbox).filter_by(turn_id=copied_turn.id).count() == 0
    nested = l.store.branch_reply(branch, copied_turn.id, "after")


def test_retry_uses_selected_original_prompt_and_preserves_original_thread(ledger):
    l = ledger
    source = l.store.submit(str(l.thread.uuid), payload(text="Original question"))
    source.status, source.active_key = "completed", None
    l.db.session.commit()
    later = l.store.submit(
        str(l.thread.uuid), payload("later", "Unrelated later question")
    )
    l.store.cancel(later)
    branch = l.store.branch_reply(l.thread, source.id, "retry")
    rerun = (
        l.db.session.query(l.Turn)
        .filter_by(session_id=branch.id, status="queued")
        .one()
    )
    state = l.store.loads(rerun.state_json)
    assert state["input_text"] == "Original question"
    assert l.db.session.query(l.Outbox).filter_by(turn_id=rerun.id).count() == 1
    assert source.session_id == l.thread.id and source.status == "completed"


@pytest.mark.parametrize("status", ["completed", "in_progress", "failed"])
def test_retry_never_repeats_dispatched_writes(ledger, status):
    l = ledger
    source = l.store.submit(str(l.thread.uuid), payload())
    source.status, source.active_key = "completed", None
    state = l.store.loads(source.state_json)
    state["checkpoint"]["calls"] = {
        "save": {"effect": "write", "status": status, "attempts": 1}
    }
    source.state_json = l.store.dumps(state)
    l.db.session.commit()
    with pytest.raises(l.store.RuntimeRequestError, match="Fork chat"):
        l.store.branch_reply(l.thread, source.id, "retry")


def test_work_activity_uses_active_duration_and_excludes_private_reasoning(ledger):
    from superset.ai_chat.api import session_to_dict
    from superset.models.ai_chat import AiChatMessage

    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    turn.status, turn.active_key = "completed", None
    state = l.store.loads(turn.state_json)
    state["checkpoint"]["active_seconds"] = 524.9
    state["messages"] = [
        {"role": "assistant", "reasoning_content": "private-hidden-thought"}
    ]
    turn.state_json = l.store.dumps(state)
    item = l.Item(
        turn_id=turn.id,
        kind="tool",
        status="completed",
        payload_json=l.store.dumps(
            {"tool": "focalbi__health_check", "result": {"status": "healthy"}}
        ),
    )
    reply = AiChatMessage(session_id=l.thread.id, role="assistant", content="Healthy")
    reply.extra = {"runtime_turn_id": turn.id}
    l.db.session.add_all([item, reply])
    l.db.session.commit()
    snapshot = l.store.snapshot(turn)
    assert snapshot["activity"]["duration_seconds"] == 524.9
    assert len(snapshot["activity"]["items"]) == 1
    assert "private-hidden-thought" not in l.store.dumps(snapshot)
    l.db.session.refresh(l.thread)
    serialized = session_to_dict(l.thread, include_messages=True)
    published = next(m for m in serialized["messages"] if m["role"] == "assistant")
    assert published["extra"]["activity"]["duration_seconds"] == 524.9
    branch = l.store.fork(l.thread, turn.id, include_turn=True)
    copied = l.db.session.query(l.Turn).filter_by(session_id=branch.id).one()
    assert (
        l.store.snapshot(copied)["activity"]["items"][0]["payload"]["tool"]
        == "focalbi__health_check"
    )


def test_edit_resend_rewinds_to_selected_input_and_preserves_original(ledger):
    l = ledger
    from superset.models.ai_chat import AiChatMessage
    from superset.ai_runtime.workflows import workflow_catalog

    workflow = workflow_catalog()[0]["id"]
    prior = l.store.submit(str(l.thread.uuid), payload(text="Earlier question"))
    prior.status, prior.active_key = "completed", None
    state = l.store.loads(prior.state_json)
    state["messages"] = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier evidence"},
    ]
    prior.state_json = l.store.dumps(state)
    l.db.session.commit()
    incoming = {
        **payload("selected", "Original selected question"),
        "workflow_ids": [workflow],
    }
    target = l.store.submit(str(l.thread.uuid), incoming)
    target.status, target.active_key = "completed", None
    reply = AiChatMessage(
        session_id=l.thread.id, role="assistant", content="Old selected answer"
    )
    reply.extra = {"runtime_turn_id": target.id}
    l.db.session.add(reply)
    l.db.session.commit()
    later = l.store.submit(str(l.thread.uuid), payload("later", "Later question"))
    l.store.cancel(later)
    original_ids = [m.id for m in l.thread.messages]
    branch = l.store.branch_reply(
        l.thread, target.id, "edit", edited_input="  Revised question  "
    )
    l.db.session.refresh(branch)
    queued = (
        l.db.session.query(l.Turn)
        .filter_by(session_id=branch.id, status="queued")
        .one()
    )
    revised = l.store.loads(queued.state_json)
    assert revised["input_text"] == "Revised question"
    assert revised["messages"] == []
    assert revised["workflow_ids"] == [workflow]
    contents = [m.content for m in branch.messages]
    assert "Revised question" in contents
    assert "Original selected question" not in contents
    assert "Old selected answer" not in contents and "Later question" not in contents
    assert [m.id for m in l.thread.messages] == original_ids
    assert l.db.session.query(l.Outbox).filter_by(turn_id=queued.id).count() == 1


@pytest.mark.parametrize("value", [" ", None, "x" * 64001])
def test_edit_rejects_invalid_input_without_creating_branch(ledger, value):
    from superset.models.ai_chat import AiChatSession

    l = ledger
    source = l.store.submit(str(l.thread.uuid), payload())
    source.status, source.active_key = "completed", None
    l.db.session.commit()
    count = l.db.session.query(AiChatSession).count()
    with pytest.raises(l.store.RuntimeRequestError, match="Input must contain"):
        l.store.branch_reply(l.thread, source.id, "edit", edited_input=value)
    assert l.db.session.query(AiChatSession).count() == count


def test_activity_upserts_publish_full_items_and_keep_terminal_truth(
    ledger, monkeypatch
):
    from superset.ai_runtime import engine

    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())

    async def fake_run(state, **callbacks):
        emit = callbacks["emit"]
        emit("reasoning_status", {"generation_id": "g1", "message": "Thinking"})
        emit(
            "reasoning_summary",
            {
                "generation_id": "g1",
                "summary_id": "s1",
                "message": "Checking",
                "completed": False,
            },
        )
        emit(
            "reasoning_summary",
            {
                "generation_id": "g1",
                "summary_id": "s1",
                "message": "Checking datasets",
                "completed": False,
            },
        )
        emit("tool_started", {"call_id": "c1", "tool": "list_datasets"})
        emit(
            "tool_completed",
            {"call_id": "c1", "tool": "list_datasets", "isError": True},
        )
        return {
            "status": "cancelled",
            "content": "",
            "messages": [],
            "checkpoint": {"calls": {}},
        }

    monkeypatch.setattr(engine, "run_turn", fake_run)
    l.runner.execute_turn(turn.id)
    l.db.session.refresh(turn)
    public = l.store.snapshot(turn)
    items = public["activity"]["items"]
    assert len(items) == 3
    summary = next(item for item in items if item["kind"] == "reasoning_summary")
    assert summary["payload"]["message"] == "Checking datasets"
    assert summary["status"] == "cancelled"
    assert next(item for item in items if item["kind"] == "tool")["status"] == "failed"
    events = (
        l.db.session.query(l.Event)
        .filter_by(turn_id=turn.id, event_type="activity_updated")
        .order_by(l.Event.sequence)
        .all()
    )
    assert len(events) == 5
    first = l.store.loads(events[1].payload_json)["item"]
    second = l.store.loads(events[2].payload_json)["item"]
    assert first["id"] == second["id"] == summary["id"]
    assert first["payload"]["message"] == "Checking"
    assert second["payload"]["message"] == "Checking datasets"


def test_worker_recovery_closes_abandoned_activity_before_new_generation(ledger):
    from datetime import timedelta

    ctx = ledger
    turn = ctx.store.submit(str(ctx.thread.uuid), payload())
    turn.status = "running"
    turn.lease_owner = "lost-worker"
    turn.lease_expires = ctx.store.now() - timedelta(seconds=120)
    phase = ctx.Item(
        turn_id=turn.id,
        kind="reasoning_status",
        status="running",
        payload_json=ctx.store.dumps({"generation_id": "old"}),
    )
    ctx.db.session.add(phase)
    ctx.db.session.commit()
    assert ctx.runner.recover_stale() == 1
    ctx.db.session.refresh(turn)
    assert turn.status == "queued"
    assert ctx.store.snapshot(turn)["activity"]["items"][0]["status"] == "interrupted"
    event = (
        ctx.db.session.query(ctx.Event)
        .filter_by(turn_id=turn.id, event_type="activity_updated")
        .one()
    )
    assert ctx.store.loads(event.payload_json)["item"]["id"] == phase.id
    assert (
        ctx.store.loads(event.payload_json)["item"]["payload"]["interruption_reason"]
        == "worker_lease_expired"
    )


def test_opted_in_reasoning_is_durable_visible_activity_not_answer_text(
    ledger, monkeypatch
):
    from superset.ai_runtime import engine

    ctx = ledger
    turn = ctx.store.submit(str(ctx.thread.uuid), payload())

    async def fake_run(state, **callbacks):
        callbacks["emit"](
            "reasoning_status", {"generation_id": "g", "message": "Thinking"}
        )
        callbacks["emit"](
            "model_reasoning",
            {
                "generation_id": "g",
                "message": "Checking allowed datasets",
                "completed": False,
            },
        )
        callbacks["emit"](
            "model_reasoning",
            {
                "generation_id": "g",
                "message": "Checking allowed datasets and page counts",
                "completed": True,
            },
        )
        callbacks["emit"](
            "reasoning_status",
            {"generation_id": "g", "message": "Thinking", "completed": True},
        )
        return {
            "status": "completed",
            "content": "Answer only",
            "messages": [],
            "checkpoint": {"calls": {}},
        }

    monkeypatch.setattr(engine, "run_turn", fake_run)
    ctx.runner.execute_turn(turn.id)
    ctx.db.session.refresh(turn)
    snapshot = ctx.store.snapshot(turn)
    rows = [i for i in snapshot["activity"]["items"] if i["kind"] == "model_reasoning"]
    assert len(rows) == 1
    assert rows[0]["payload"]["message"] == "Checking allowed datasets and page counts"
    assert snapshot["content"] == "Answer only"


def test_worker_failure_does_not_regenerate_partially_displayed_model_reasoning(ledger):
    from datetime import timedelta

    ctx = ledger
    turn = ctx.store.submit(str(ctx.thread.uuid), payload())
    turn.status = "running"
    turn.lease_owner = "lost-worker"
    turn.lease_expires = ctx.store.now() - timedelta(seconds=120)
    ctx.db.session.add_all(
        [
            ctx.Item(
                turn_id=turn.id,
                kind="reasoning_status",
                status="running",
                payload_json=ctx.store.dumps({"generation_id": "g"}),
            ),
            ctx.Item(
                turn_id=turn.id,
                kind="model_reasoning",
                status="running",
                payload_json=ctx.store.dumps(
                    {"generation_id": "g", "message": "Partial visible reasoning"}
                ),
            ),
        ]
    )
    ctx.db.session.commit()
    assert ctx.runner.recover_stale() == 1
    ctx.db.session.refresh(turn)
    assert turn.status == "queued"
    assert turn.error_json is None
    assert ctx.store.snapshot(turn)["activity"]["items"][0]["status"] == "interrupted"


@pytest.mark.parametrize("mode,expected", [("after", 2), ("edit", 0), ("retry", 0)])
def test_native_branch_uses_sdk_boundary_not_legacy_history(
    ledger, monkeypatch, mode, expected
):
    import asyncio
    from flask import current_app
    from superset.ai_runtime.native_session import application_models, FocalSession

    l = ledger
    monkeypatch.setitem(current_app.config, "AI_RUNTIME_EXECUTION_ENGINE", "sdk_native")
    rows = application_models()
    rows[0].metadata.create_all(l.db.engine)
    try:
        source = l.store.submit(str(l.thread.uuid), payload())
        session = FocalSession(
            str(l.thread.uuid),
            database=l.db.session,
            models=rows,
            owner_id=1,
            post_id=11,
            binding="test",
            turn_id=source.id,
            guard=lambda: None,
        )
        asyncio.run(
            session.add_items(
                [
                    {"role": "user", "content": "question"},
                    {"role": "assistant", "content": "answer"},
                ]
            )
        )
        source.status, source.active_key = "completed", None
        value = l.store.loads(source.state_json)
        assert value["messages"] == []
        value["checkpoint"].update(
            session_end=2, sdk_state="private-checkpoint", grants={"call": "grant"}
        )
        source.state_json = l.store.dumps(value)
        l.db.session.add(
            l.Item(
                turn_id=source.id,
                kind="tool",
                status="completed",
                external_id="source-call",
                payload_json="{}",
            )
        )
        l.db.session.commit()
        branch = l.store.branch_reply(l.thread, source.id, mode, edited_input="edited")
        copied = (
            l.db.session.query(rows[1]).filter_by(session_id=str(branch.uuid)).count()
        )
        assert copied == expected
        assert (
            l.db.session.query(rows[1]).filter_by(session_id=str(l.thread.uuid)).count()
            == 2
        )
        if mode == "after":
            cloned = l.db.session.query(l.Turn).filter_by(session_id=branch.id).one()
            cp = l.store.loads(cloned.state_json)["checkpoint"]
            assert (
                l.db.session.query(l.Item)
                .filter_by(turn_id=cloned.id, external_id="source-call")
                .count()
                == 1
            )
            assert "sdk_state" not in cp and "grants" not in cp
    finally:
        l.db.session.rollback()
        rows[0].metadata.drop_all(l.db.engine)


def test_native_cancel_seals_pending_sdk_call_without_dispatch(ledger, monkeypatch):
    import asyncio
    from flask import current_app
    from superset.ai_runtime.native_session import application_models, FocalSession

    l = ledger
    monkeypatch.setitem(current_app.config, "AI_RUNTIME_EXECUTION_ENGINE", "sdk_native")
    rows = application_models()
    rows[0].metadata.create_all(l.db.engine)
    try:
        turn = l.store.submit(str(l.thread.uuid), payload())
        session = FocalSession(
            str(l.thread.uuid),
            database=l.db.session,
            models=rows,
            owner_id=1,
            post_id=11,
            binding="test",
            turn_id=turn.id,
            guard=lambda: None,
        )
        asyncio.run(
            session.add_items(
                [
                    {"role": "user", "content": "question"},
                    {
                        "type": "function_call",
                        "call_id": "pending",
                        "name": "read",
                        "arguments": "{}",
                    },
                ]
            )
        )
        value = l.store.loads(turn.state_json)
        value["checkpoint"].update(sdk_session_id=str(l.thread.uuid), calls={})
        turn.state_json = l.store.dumps(value)
        l.db.session.commit()
        l.store.cancel(turn)
        assert turn.status == "cancelled"
        saved = asyncio.run(session.get_items())
        assert (
            saved[-1]["call_id"] == "pending"
            and saved[-1]["type"] == "function_call_output"
        )
        assert "without a recorded outcome" in saved[-1]["output"]
    finally:
        l.db.session.rollback()
        rows[0].metadata.drop_all(l.db.engine)


def test_native_stale_stream_restores_durable_content_and_replays_reset(ledger):
    l = ledger
    turn = l.store.submit(str(l.thread.uuid), payload())
    turn.status, turn.lease_owner = "running", "abandoned"
    turn.lease_expires = l.store.now() - timedelta(minutes=2)
    turn.content = "uncheckpointed partial"
    value = l.store.loads(turn.state_json)
    value.update(execution_engine="sdk_native")
    value["checkpoint"].update(content="durable content", native_started=True, calls={})
    turn.state_json = l.store.dumps(value)
    l.db.session.commit()
    assert l.runner.recover_stale() == 1
    assert turn.status == "queued" and turn.content == "durable content"
    assert (
        l.db.session.query(l.Event)
        .filter_by(turn_id=turn.id, event_type="message_reset")
        .count()
        == 1
    )


def test_recovery_reset_updates_reload_snapshot_before_completion(ledger, monkeypatch):
    from superset.ai_runtime import engine

    context = ledger
    turn = context.store.submit(str(context.thread.uuid), payload())

    async def fake_run(state, **callbacks):
        callbacks["emit"]("message_delta", {"content": "obsolete partial"})
        callbacks["emit"]("message_reset", {"content": "recovered"})
        context.db.session.refresh(turn)
        assert context.store.snapshot(turn)["content"] == "recovered"
        return {
            "status": "completed",
            "content": "recovered",
            "checkpoint": {"calls": {}},
        }

    monkeypatch.setattr(engine, "run_turn", fake_run)
    context.runner.execute_turn(turn.id)
    assert turn.status == "completed"


def test_only_native_contract_is_selected_despite_legacy_configuration(
    ledger, monkeypatch
):
    from flask import current_app

    monkeypatch.setitem(current_app.config, "AI_RUNTIME_EXECUTION_ENGINE", "legacy")
    turn = ledger.store.submit(
        str(ledger.thread.uuid), {**payload(), "execution_engine": "legacy"}
    )
    state = ledger.store.loads(turn.state_json)
    assert state["execution_engine"] == "sdk_native"
    assert state["execution_version"] == 3
    assert state["messages"] == []
    assert state["checkpoint"] == {}


def test_deleting_conversation_removes_only_its_sdk_history(ledger, monkeypatch):
    import asyncio
    from uuid import UUID
    from superset.ai_runtime.native_session import FocalSession, application_models
    from superset.commands.ai_chat.delete import DeleteAiChatSessionCommand
    from superset.daos.ai_chat import AiChatSessionDAO

    ctx = ledger
    rows = application_models()
    sdk = FocalSession(
        str(ctx.thread.uuid),
        database=ctx.db.session,
        models=rows,
        owner_id=1,
        post_id=11,
        binding="test",
        turn_id="test",
        guard=lambda: None,
    )
    asyncio.run(sdk.add_items([{"role": "user", "content": "private history"}]))
    ctx.db.session.add(
        rows[0](id="other", owner_id=2, post_id=12, binding="other", revision=0)
    )
    ctx.db.session.commit()
    monkeypatch.setattr(AiChatSessionDAO, "find_by_uuid", lambda uuid: ctx.thread)
    DeleteAiChatSessionCommand(UUID(str(ctx.thread.uuid))).run()
    assert ctx.db.session.query(rows[1]).count() == 0
    assert ctx.db.session.query(rows[0]).filter_by(id="other").count() == 1


def test_retired_execution_contracts_fail_without_model_or_tool_calls():
    import asyncio
    from superset.ai_runtime.engine import run_turn
    from superset.ai_runtime.contracts import AiRuntimeError

    for engine in ("legacy", "agents_sdk", None):
        with pytest.raises(AiRuntimeError, match="predates the SDK reset"):
            asyncio.run(run_turn({"execution_engine": engine}))


def test_stream_checks_renew_lease_when_heartbeat_timer_has_not_run(
    ledger, monkeypatch
):
    from superset.ai_runtime import engine

    ctx = ledger
    turn = ctx.store.submit(str(ctx.thread.uuid), payload())
    ticks = [100.0]
    monkeypatch.setattr(ctx.runner.time, "monotonic", lambda: ticks[0])

    async def fake_run(state, **callbacks):
        turn.lease_expires = ctx.store.now() + timedelta(seconds=1)
        ctx.db.session.commit()
        ticks[0] += 11
        assert callbacks["cancelled"]() is False
        ctx.db.session.refresh(turn)
        assert turn.lease_expires >= ctx.store.now() + timedelta(seconds=50)
        return {
            "status": "completed",
            "content": "Done",
            "messages": [],
            "checkpoint": {
                "calls": {},
                "context_usage": {"model": "test", "input_tokens": 100},
            },
        }

    monkeypatch.setattr(engine, "run_turn", fake_run)
    ctx.runner.execute_turn(turn.id)
    ctx.db.session.refresh(turn)
    assert turn.status == "completed"
    assert ctx.store.snapshot(turn)["context_usage"] == {
        "model": "test",
        "input_tokens": 100,
    }


@pytest.mark.parametrize("mode", ["ask", "full_access"])
def test_confirmation_mode_is_validated_and_snapshotted(ledger: Any, mode: str) -> None:
    value = {**payload(), "approval_mode": mode}
    turn = ledger.store.submit(str(ledger.thread.uuid), value)
    assert ledger.store.snapshot(turn)["approval_mode"] == mode
    assert ledger.store.loads(turn.state_json)["approval_mode"] == mode


@pytest.mark.parametrize("mode", ["admin", True, None, ["full_access"]])
def test_invalid_confirmation_modes_are_rejected(ledger: Any, mode: Any) -> None:
    with pytest.raises(ledger.store.RuntimeRequestError, match="Choose"):
        ledger.store.submit(
            str(ledger.thread.uuid), {**payload(), "approval_mode": mode}
        )


def pending_approval(ledger: Any) -> tuple[Any, Any]:
    turn = ledger.store.submit(str(ledger.thread.uuid), payload())
    details = {
        "kind": "approval",
        "call_id": "call",
        "fingerprint": "bound",
        "expires_at": (ledger.store.now() - timedelta(minutes=5)).isoformat() + "Z",
    }
    state = ledger.store.loads(turn.state_json)
    state["checkpoint"] = {"pending_request": details}
    state["pending_request"] = details
    turn.state_json = ledger.store.dumps(state)
    turn.status = "waiting_approval"
    item = ledger.Item(
        turn_id=turn.id,
        kind="request",
        status="pending",
        payload_json=ledger.store.dumps(details),
    )
    ledger.db.session.add(item)
    ledger.db.session.commit()
    return turn, item


def test_expired_approval_refresh_does_not_grant_or_dispatch(ledger: Any) -> None:
    turn, item = pending_approval(ledger)
    data = {
        "expected_turn_id": turn.id,
        "idempotency_key": "approval",
        "request_id": item.id,
        "response": {"decision": "accept"},
    }
    with pytest.raises(ledger.store.RuntimeRequestError, match="expired"):
        ledger.store.input_turn(turn, data)
    ledger.store.input_turn(turn, {**data, "response": {"decision": "refresh"}})
    state = ledger.store.loads(turn.state_json)
    assert turn.status == "queued"
    assert state["approved_scopes"] == []
    assert state["pending_response"] == {"decision": "refresh"}
    assert item.status == "completed"


def test_full_access_resumes_expired_approval_without_reusing_its_grant(
    ledger: Any,
) -> None:
    turn, item = pending_approval(ledger)
    ledger.store.set_approval_mode(turn, "full_access")
    assert turn.status == "queued"
    assert item.status == "completed"
    state = ledger.store.loads(turn.state_json)
    assert state["approval_mode"] == "full_access"
    assert state["approved_scopes"] == []
    assert state["checkpoint"]["pending_request"]["fingerprint"] == "bound"
    assert (
        ledger.db.session.query(ledger.Item)
        .filter_by(turn_id=turn.id, kind="approval_mode")
        .count()
        == 1
    )


def test_mode_changes_reach_active_worker_and_cannot_be_smuggled_in_steering(
    ledger: Any,
) -> None:
    turn = ledger.store.submit(str(ledger.thread.uuid), payload())
    turn.status = "running"
    ledger.db.session.commit()
    ledger.store.set_approval_mode(turn, "full_access")
    updates = (
        ledger.db.session.query(ledger.Item)
        .filter_by(turn_id=turn.id, kind="user_input")
        .all()
    )
    assert [ledger.store.loads(item.payload_json) for item in updates] == [
        {"_approval_mode": "full_access"}
    ]
    with pytest.raises(ledger.store.RuntimeRequestError, match="control"):
        ledger.store.input_turn(
            turn,
            {
                "expected_turn_id": turn.id,
                "idempotency_key": "hidden",
                "input": "x",
                "_approval_mode": "full_access",
            },
        )
    ledger.scope["post"] = 12
    with pytest.raises(ledger.store.RuntimeRequestError):
        ledger.store.get_turn(turn.id)

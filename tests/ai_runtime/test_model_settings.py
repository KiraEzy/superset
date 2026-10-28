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
"""Model budgets survive reloads and reach the SDK wire without changing old turns."""

import asyncio
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import test_model_catalog as catalog_tests
import test_native_context as native_tests
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import current_app
from sqlalchemy import create_engine, text

from superset.utils import json

ledger = catalog_tests.ledger
test_app = catalog_tests.test_app
database = native_tests.database

VALUES = {
    "context_window_tokens": 65536,
    "response_tokens": 8192,
    "tool_result_tokens": 2048,
}


def test_settings_snapshot_and_same_named_connections_are_independent(
    ledger, monkeypatch
):
    from superset.ai_runtime import model_catalog, model_settings, settings

    connection, first = catalog_tests.add_model(ledger)
    connection_before = (connection.label, connection.revision, connection.config_json)
    _, other = catalog_tests.add_model(ledger)
    old = ledger.store.submit(
        str(ledger.thread.uuid), {**catalog_tests.payload(), "model_id": first.id}
    )
    old_state = ledger.store.loads(old.state_json)
    old.status, old.active_key = "completed", None
    ledger.db.session.commit()
    model_settings.save(first.id, {"values": VALUES, "revision": 0})
    # A stale Python override cannot overwrite database values, including reset.
    monkeypatch.setitem(
        current_app.config,
        "AI_RUNTIME_MODEL_CONTEXT_LIMITS",
        {"model": {"context_window_tokens": 1000000}},
    )
    new = ledger.store.submit(
        str(ledger.thread.uuid), {**catalog_tests.payload("next"), "model_id": first.id}
    )
    new_state = ledger.store.loads(new.state_json)
    assert all(new_state["budgets"][key] == value for key, value in VALUES.items())
    assert ledger.store.loads(old.state_json) == old_state
    other_config = model_catalog.resolve(other.id, {})
    assert settings.limits("model", other_config)["context_window_tokens"] == 32768
    with pytest.raises(model_settings.ModelSettingsConflictError):
        model_settings.save(first.id, {"values": VALUES, "revision": 0})
    model_settings.save(first.id, {"reset": True, "revision": 1})
    config = model_catalog.resolve(first.id, {})
    assert settings.limits("model", config)["context_window_tokens"] == 32768
    assert config["model_settings_revision"] == 2
    assert (
        connection.label,
        connection.revision,
        connection.config_json,
    ) == connection_before


@pytest.mark.parametrize(
    "patch",
    [
        {"context_window_tokens": 4096},
        {"response_tokens": -1},
        {"response_tokens": True},
        {"response_tokens": 1.5},
        {"tool_result_tokens": "4096"},
        {"context_window_tokens": 100000001},
        {"unknown": 5},
    ],
)
def test_invalid_settings_do_not_change_persisted_values(
    ledger: Any, patch: dict[str, Any]
) -> None:
    from superset.ai_runtime import model_settings

    _, model = catalog_tests.add_model(ledger)
    with pytest.raises(ValueError, match="tokens|Token|limits"):
        model_settings.save(model.id, {"values": {**VALUES, **patch}, "revision": 0})
    ledger.db.session.expire_all()
    assert model.settings_revision == 0
    assert model_settings.overrides(model) == {}


def test_settings_route_admin_validation_and_conflict(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from superset.ai_runtime import model_catalog
    from superset.views.ai import config_api

    _, model = catalog_tests.add_model(ledger)
    api = config_api.AIConnectionRestApi.__new__(config_api.AIConnectionRestApi)
    handler = inspect.unwrap(config_api.AIConnectionRestApi.model_settings)
    monkeypatch.setattr(
        config_api, "security_manager", SimpleNamespace(is_admin=lambda: False)
    )
    assert handler(api, model.id)[1] == 403
    monkeypatch.setattr(
        config_api, "security_manager", SimpleNamespace(is_admin=lambda: True)
    )
    assert handler(api, model.id)[1] == 400
    with current_app.test_request_context(json={"values": VALUES, "revision": 0}):
        assert handler(api, model.id)[1] == 200
        assert handler(api, model.id)[1] == 409
    public = model_catalog.catalogue()
    assert "runtime_settings" not in public["models"][0]
    admin = model_catalog.catalogue(admin=True)
    assert admin["models"][0]["runtime_settings"]["values"] == VALUES


def test_migration_copies_existing_operator_profiles_once(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = (
        Path(__file__).parents[2]
        / "superset/migrations/versions"
        / "2026-10-26_01-00_f7a8b9c0d1e2_model_runtime_settings.py"
    )
    spec = importlib.util.spec_from_file_location("model_settings_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    monkeypatch.setitem(
        current_app.config,
        "AI_RUNTIME_MODEL_CONTEXT_LIMITS",
        {
            "deepseek-v4-flash": {
                "context_window_tokens": 1000000,
                "response_tokens": 384000,
            }
        },
    )
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE ai_model (id TEXT PRIMARY KEY, model_name TEXT)")
        )
        conn.execute(
            text(
                "INSERT INTO ai_model VALUES ('one', 'deepseek-v4-flash'), "
                "('two', 'qwen')"
            )
        )
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(conn))
        )
        migration.upgrade()
        rows = conn.execute(
            text(
                "SELECT model_name, runtime_settings_json, settings_revision "
                "FROM ai_model ORDER BY id"
            )
        ).all()
        assert json.loads(rows[0][1]) == {
            "context_window_tokens": 1000000,
            "response_tokens": 384000,
        }
        assert json.loads(rows[1][1]) == {}
        assert rows[0][2] == rows[1][2] == 0
    engine.dispose()


def test_saved_model_limits_reach_actual_sdk_wire(ledger: Any, database: Any) -> None:
    from superset.ai_runtime import model_settings

    _, model = catalog_tests.add_model(ledger)
    model_settings.save(model.id, {"values": VALUES, "revision": 0})
    turn = ledger.store.submit(
        str(ledger.thread.uuid), {**catalog_tests.payload(), "model_id": model.id}
    )
    saved = ledger.store.loads(turn.state_json)
    requests = []

    async def provider(request: Any) -> Any:
        requests.append(json.loads(request.content))
        return native_tests.n.streamed_response()

    value = native_tests.state(database, provider)
    value["config"] = saved["config"]
    value["budgets"] = saved["budgets"]
    result = asyncio.run(native_tests.run(value))
    assert result["status"] == "completed"
    assert len(requests) == 1
    assert (
        requests[0].get("max_tokens", requests[0].get("max_completion_tokens")) == 8192
    )

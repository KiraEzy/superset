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
"""Persisted chart reference, permission and preview-normalization regressions."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_engine
import test_store

ledger = test_store.ledger
test_app = test_store.test_app


def seed(ledger_state, monkeypatch):
    from superset.ai_runtime import artifact_memory

    turn = ledger_state.store.submit(
        str(ledger_state.thread.uuid), test_store.payload()
    )
    config = {
        "chart_type": "xy",
        "x": {"name": "district"},
        "y": [{"name": "population", "aggregate": "SUM"}],
        "filters": [{"column": "region", "op": "==", "value": "Kowloon"}],
        "orientation": "vertical",
    }
    state = ledger_state.store.loads(turn.state_json)
    state["checkpoint"]["calls"] = {
        "preview-call": {"arguments": {"request": {"dataset_id": 31, "config": config}}}
    }
    turn.state_json = ledger_state.store.dumps(state)
    row = ledger_state.Artifact(
        id=str(uuid4()),
        turn_id=turn.id,
        artifact_type="chart",
        title="Population",
        version=1,
        payload_json=ledger_state.store.dumps(
            {
                "form_data": {
                    "datasource": "31__table",
                    "viz_type": "echarts_timeseries_bar",
                    "metrics": ["population"],
                    "adhoc_filters": [{"subject": "region", "comparator": "Kowloon"}],
                },
                "form_data_key": "preview-key",
            }
        ),
        provenance_json=ledger_state.store.dumps(
            {"call_id": "preview-call", "connection_id": "focalbi"}
        ),
    )
    ledger_state.db.session.add(row)
    ledger_state.db.session.commit()
    checked = []
    monkeypatch.setattr(
        ledger_state.store, "validate_context", lambda refs: checked.extend(refs)
    )
    return artifact_memory, turn, row, config, checked


def test_exact_baseline_and_source_config_survive_refresh(ledger, monkeypatch):
    memory, turn, row, config, checked = seed(ledger, monkeypatch)
    ledger.db.session.expire_all()
    artifact = memory.read(turn)
    assert artifact["id"] == row.id
    assert artifact["source_request"]["config"] == config
    assert (
        artifact["payload"]["form_data"]["adhoc_filters"][0]["comparator"] == "Kowloon"
    )
    assert checked
    assert all(ref == {"type": "dataset", "id": 31} for ref in checked)
    assert memory.index(turn)[0]["id"] == row.id


def test_artifact_lookup_cannot_cross_user_post_or_thread(ledger, monkeypatch):
    memory, turn, row, _, _ = seed(ledger, monkeypatch)
    for fields in ({"post_id": 12}, {"user_id": 999}, {"session_id": 999}):
        wrong = SimpleNamespace(
            session_id=turn.session_id, user_id=turn.user_id, post_id=turn.post_id
        )
        for key, value in fields.items():
            setattr(wrong, key, value)
        assert memory.index(wrong) == []
        with pytest.raises(ledger.store.RuntimeRequestError):
            memory.read(wrong, row.id)


def test_revoked_dataset_access_hides_artifact(ledger, monkeypatch):
    memory, turn, row, _, _ = seed(ledger, monkeypatch)

    def deny(refs):
        raise ledger.store.RuntimeRequestError("Unavailable", 403, "context_denied")

    monkeypatch.setattr(ledger.store, "validate_context", deny)
    assert memory.index(turn) == []
    with pytest.raises(ledger.store.RuntimeRequestError):
        memory.read(turn, row.id)


def test_preview_update_result_produces_a_chart_artifact_without_server_changes():
    artifacts = __import__(
        f"{test_engine.PACKAGE}.artifacts", fromlist=["extract_artifacts"]
    )
    result = {
        "isError": False,
        "structuredContent": {
            "chart": {
                "id": None,
                "slice_name": "Changed",
                "viz_type": "echarts_timeseries_bar",
            },
            "form_data_key": "new",
            "previous_form_data_key": "old",
            "explore_url": "/explore/?form_data_key=new",
        },
    }
    chart = next(
        a
        for a in artifacts.extract_artifacts("update_chart_preview", "c", result)
        if a["type"] == "chart"
    )
    assert chart["data"]["form_data_key"] == "new"
    assert chart["data"]["previous_form_data_key"] == "old"


def test_native_preview_cache_hydration_preserves_exact_form_data(ledger, monkeypatch):
    from superset.ai_runtime import artifact_memory
    from superset.commands.explore.form_data.get import GetFormDataCommand

    form_data = {
        "datasource": "31__table",
        "viz_type": "echarts_timeseries_bar",
        "orientation": "horizontal",
        "metrics": ["population"],
        "adhoc_filters": [{"subject": "region", "comparator": "Kowloon"}],
    }
    monkeypatch.setattr(
        GetFormDataCommand, "run", lambda self: ledger.store.dumps(form_data)
    )
    hydrated = artifact_memory.hydrate_preview(
        {"form_data_key": "key", "viz_type": "echarts_timeseries_bar"}
    )
    assert hydrated["form_data"] == form_data
    assert artifact_memory.hydrate_preview(hydrated) == hydrated


def test_metadata_read_reuses_preview_and_does_not_reset_version(ledger, monkeypatch):
    memory, turn, row, _, _ = seed(ledger, monkeypatch)
    row.version = 2
    ledger.db.session.commit()
    payload = ledger.store.loads(row.payload_json)
    assert memory.find_preview(turn, payload).id == row.id
    duplicate = ledger.Artifact(
        id=str(uuid4()),
        turn_id=turn.id,
        artifact_type="chart",
        title="Metadata",
        version=1,
        payload_json=row.payload_json,
        provenance_json=row.provenance_json,
    )
    ledger.db.session.add(duplicate)
    ledger.db.session.commit()
    refs = memory.index(turn)
    assert len(refs) == 1
    assert refs[0]["version"] == 2
    assert memory.read(turn)["id"] == row.id


def test_later_metadata_artifact_recovers_originating_config(ledger, monkeypatch):
    memory, first, original, config, _ = seed(ledger, monkeypatch)
    first.status, first.active_key = "completed", None
    ledger.db.session.commit()
    second = ledger.store.submit(
        str(ledger.thread.uuid), test_store.payload("follow-up")
    )
    state = ledger.store.loads(second.state_json)
    state["checkpoint"]["calls"] = {
        "metadata": {"arguments": {"request": {"form_data_key": "preview-key"}}}
    }
    second.state_json = ledger.store.dumps(state)
    row = ledger.Artifact(
        id=str(uuid4()),
        turn_id=second.id,
        artifact_type="chart",
        title="Metadata",
        version=1,
        payload_json=original.payload_json,
        provenance_json=ledger.store.dumps(
            {"call_id": "metadata", "connection_id": "focalbi"}
        ),
    )
    ledger.db.session.add(row)
    ledger.db.session.commit()
    assert memory.read(second, row.id)["source_request"]["config"] == config


def test_preview_schema_validation_rejects_hallucinated_metric():
    from superset.ai_runtime.artifact_memory import validate_form_columns
    from superset.ai_runtime.contracts import AiRuntimeError

    form = {
        "x_axis": "region",
        "metrics": [
            {
                "expressionType": "SIMPLE",
                "column": {"column_name": "count"},
                "aggregate": "SUM",
            }
        ],
    }
    with pytest.raises(AiRuntimeError, match="Invalid chart references: count"):
        validate_form_columns(form, {"region"}, set())
    form["metrics"] = [{"expressionType": "SQL", "sqlExpression": "COUNT(*)"}]
    validate_form_columns(form, {"region"}, set())

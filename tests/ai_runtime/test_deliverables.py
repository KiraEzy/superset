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
"""Durable presentation, source-success and actor/post isolation contracts."""

from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import test_store

ledger = test_store.ledger
test_app = test_store.test_app


def seed(ledger: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, Any]:
    from superset.ai_runtime import deliverables
    from superset.models.ai_runtime import AiRuntimeArtifact

    turn = ledger.store.submit(str(ledger.thread.uuid), test_store.payload())
    monkeypatch.setattr(ledger.store, "validate_context", lambda refs: refs)

    def add(
        kind: str = "chart",
        saved: bool = True,
        identity: int = 12,
        status: str = "completed",
        payload: dict[str, Any] | None = None,
        connection: str = "focalbi",
    ) -> Any:
        call = str(uuid4())
        value = (
            payload
            if payload is not None
            else (
                {"slice_id": identity, "viz_type": "echarts_timeseries_bar"}
                if kind == "chart"
                else {"id": identity}
            )
        )
        row = AiRuntimeArtifact(
            turn_id=turn.id,
            artifact_type=kind,
            title="Result",
            payload_json=ledger.store.dumps({**value, "saved": saved}),
            provenance_json=ledger.store.dumps(
                {"connection_id": connection, "call_id": call}
            ),
        )
        state = ledger.store.loads(turn.state_json)
        state.setdefault("checkpoint", {}).setdefault("calls", {})[call] = {
            "status": status,
            "result": {"isError": status == "failed"},
        }
        turn.state_json = ledger.store.dumps(state)
        ledger.db.session.add(row)
        ledger.db.session.flush()
        return row

    return deliverables, turn, add


def test_saved_resource_deduplication_across_turns_and_restart(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    first = add()
    assert d.auto_present(turn, ledger.store.artifact_dict(first))
    latest = add()
    latest.created_on = first.created_on + timedelta(seconds=1)
    d.auto_present(turn, ledger.store.artifact_dict(latest))
    turn.status, turn.active_key = "completed", None
    ledger.db.session.commit()
    second = ledger.store.submit(str(ledger.thread.uuid), test_store.payload("second"))
    ledger.db.session.expire_all()
    items = d.listing(second)
    assert len(items) == 1 and items[0]["artifact_id"] == latest.id
    assert ledger.store.snapshot(second)["deliverables"] == items
    assert d.rows(second).count() == 2


def test_explicit_preview_and_table_publication_is_idempotent_and_immutable(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    preview = add(
        saved=False,
        payload={
            "form_data_key": "preview",
            "viz_type": "table",
            "form_data": {"datasource": "31__table"},
        },
    )
    table = add(
        kind="table",
        saved=False,
        payload={"rows": [{"total": 42}], "source_request": {"dataset_id": 31}},
    )
    original = preview.payload_json
    assert d.listing(turn) == []
    args = {"artifact_id": preview.id, "title": "Population chart"}
    first = d.present(turn, args)
    assert d.present(turn, args) == first
    d.present(turn, {"artifact_id": table.id, "title": "Final totals"})
    ledger.db.session.commit()
    ledger.db.session.expire_all()
    assert len(d.listing(turn)) == 2
    assert len(d.registrations(turn)) == 2
    assert preview.payload_json == original
    assert not d.listing(turn)[0]["saved"]


def test_preview_replacement_preserves_single_logical_entry(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)

    def preview() -> Any:
        return add(
            saved=False,
            payload={"viz_type": "table", "form_data": {"datasource": "31__table"}},
        )

    one, two = preview(), preview()
    initial = d.present(turn, {"artifact_id": one.id, "title": "First"})
    second = d.present(
        turn,
        {"artifact_id": two.id, "title": "Updated", "replaces_artifact_id": one.id},
    )
    assert second["key"] == initial["key"]
    assert d.listing(turn) == [second]
    assert d.rows(turn).count() == 2


@pytest.mark.parametrize("status", ["failed", "in_progress"])
def test_failed_or_unresolved_sources_cannot_be_presented(
    ledger: Any, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    row = add(status=status)
    with pytest.raises(ledger.store.RuntimeRequestError):
        d.present(turn, {"artifact_id": row.id, "title": "Wrong"})
    assert d.listing(turn) == []


def test_scope_and_access_are_checked_on_publish_and_reload(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    row = add()
    for key in ["session_id", "user_id", "post_id"]:
        scope = SimpleNamespace(
            session_id=turn.session_id, user_id=turn.user_id, post_id=turn.post_id
        )
        setattr(scope, key, 9999)
        assert d.listing(scope) == []
        with pytest.raises(ledger.store.RuntimeRequestError):
            d.present(scope, {"artifact_id": row.id, "title": "Denied"})
    d.present(turn, {"artifact_id": row.id, "title": "Allowed"})

    def deny(refs: Any) -> Any:
        raise ledger.store.RuntimeRequestError("Denied", 403)

    monkeypatch.setattr(ledger.store, "validate_context", deny)
    assert d.listing(turn)[0]["available"] is False
    with pytest.raises(ledger.store.RuntimeRequestError):
        d.present(turn, {"artifact_id": row.id, "title": "Denied"})


def test_distinct_resources_and_connections_never_merge(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    add(identity=12)
    add(identity=13)
    add(kind="dashboard", identity=12)
    add(identity=12, connection="other")
    entries = d.listing(turn)
    assert len(entries) == 4 and len({value["key"] for value in entries}) == 4
    assert sum(not entry["available"] for entry in entries) == 1


def test_fork_remaps_only_copied_presentations(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    row = add(
        kind="table",
        saved=False,
        payload={"rows": [{"total": 42}], "source_request": {"dataset_id": 31}},
    )
    d.present(turn, {"artifact_id": row.id, "title": "Final totals"})
    turn.status, turn.active_key = "completed", None
    ledger.db.session.commit()
    branch = ledger.store.fork(ledger.thread, turn.id, include_turn=True)
    copied = ledger.db.session.query(ledger.Turn).filter_by(session_id=branch.id).one()
    entries = d.listing(copied)
    assert len(entries) == 1
    assert entries[0]["artifact_id"] != row.id
    assert entries[0]["key"] == f"visual:{entries[0]['artifact_id']}"
    assert len(d.registrations(turn)) == 1


def test_sql_is_evidence_and_cannot_be_published(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    row = add(kind="sql", payload={"sql": "SELECT 1"})
    with pytest.raises(ledger.store.RuntimeRequestError):
        d.present(turn, {"artifact_id": row.id, "title": "SQL"})
    assert d.listing(turn) == []


def test_publication_replay_and_later_title_changes_remain_ordered(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    row = add(
        kind="table",
        saved=False,
        payload={"rows": [{"total": 42}], "source_request": {"dataset_id": 31}},
    )
    first = {"artifact_id": row.id, "title": "First"}
    second = {"artifact_id": row.id, "title": "Second"}
    d.present(turn, first, "call-1")
    assert d.present(turn, first, "call-1")["title"] == "First"
    with pytest.raises(ledger.store.RuntimeRequestError):
        d.present(turn, second, "call-1")
    d.present(turn, second, "call-2")
    d.present(turn, first, "call-1")
    assert d.listing(turn)[0]["title"] == "Second"
    d.present(turn, first, "call-3")
    assert d.listing(turn)[0]["title"] == "First"
    assert len(d.registrations(turn)) == 3


def test_unsaved_preview_cannot_replace_saved_resource(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    saved = add()
    preview = add(
        saved=False,
        payload={"viz_type": "table", "form_data": {"datasource": "31__table"}},
    )
    with pytest.raises(ledger.store.RuntimeRequestError):
        d.present(
            turn,
            {
                "artifact_id": preview.id,
                "title": "Edit",
                "replaces_artifact_id": saved.id,
            },
        )


def test_dashboard_rebuild_hides_removed_drafts_without_deleting_or_title_merging(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from superset.models.ai_runtime import AiRuntimeItem

    d, turn, add = seed(ledger, monkeypatch)
    draft = add(identity=12)
    final = add(identity=13)
    standalone = add(identity=14)
    d.auto_present(turn, ledger.store.artifact_dict(draft))
    removal = AiRuntimeItem(
        turn_id=turn.id,
        kind="tool",
        status="completed",
        payload_json=ledger.store.dumps(
            {
                "tool": "focalbi__configure_dashboard_0123456789",
                "arguments": {"request": {"identifier": 20, "remove_chart_ids": [12]}},
                "result": {"structuredContent": {"success": True}},
            }
        ),
    )
    ledger.db.session.add(removal)
    ledger.db.session.flush()
    add(
        identity=12, saved=False
    )  # Inspection alone must not restore an obsolete draft.
    entries = d.listing(turn)
    assert {value["artifact_id"] for value in entries} == {final.id, standalone.id}
    assert d.rows(turn).count() == 4
    assert d.auto_present(turn, ledger.store.artifact_dict(draft)) is None
    assert len(d.listing(turn)) == 2
    d.present(
        turn,
        {"artifact_id": draft.id, "title": "Explicit standalone result"},
        "republish",
    )
    assert len(d.listing(turn)) == 3


def test_failed_dashboard_removal_does_not_hide_results_and_forks_keep_successful_removals(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from superset.models.ai_runtime import AiRuntimeItem

    d, turn, add = seed(ledger, monkeypatch)
    add(identity=12)
    keep = add(identity=13)
    removal = AiRuntimeItem(
        turn_id=turn.id,
        kind="tool",
        status="failed",
        payload_json=ledger.store.dumps(
            {
                "tool": "focalbi__configure_dashboard_0123456789",
                "arguments": {"request": {"identifier": 20, "remove_chart_ids": [12]}},
                "result": {"structuredContent": {"success": True}},
            }
        ),
    )
    ledger.db.session.add(removal)
    ledger.db.session.flush()
    assert len(d.listing(turn)) == 2
    removal.status = "completed"
    assert [entry["artifact_id"] for entry in d.listing(turn)] == [keep.id]
    turn.status, turn.active_key = "completed", None
    ledger.db.session.commit()
    branch = ledger.store.fork(ledger.thread, turn.id, include_turn=True)
    copied = ledger.db.session.query(ledger.Turn).filter_by(session_id=branch.id).one()
    assert len(d.listing(copied)) == 1


def test_later_saved_edit_can_restore_a_removed_chart(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from superset.models.ai_runtime import AiRuntimeItem

    d, turn, add = seed(ledger, monkeypatch)
    add(identity=12)
    removal = AiRuntimeItem(
        turn_id=turn.id,
        kind="tool",
        status="completed",
        payload_json=ledger.store.dumps(
            {
                "tool": "configure_dashboard",
                "arguments": {"remove_chart_ids": [12]},
                "result": {},
            }
        ),
    )
    ledger.db.session.add(removal)
    ledger.db.session.flush()
    updated = add(identity=12)
    assert [entry["artifact_id"] for entry in d.listing(turn)] == [updated.id]


def test_inspecting_an_existing_chart_does_not_publish_a_new_result(
    ledger: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, turn, add = seed(ledger, monkeypatch)
    inspected = add(identity=12, saved=False)
    assert d.listing(turn) == []
    assert d.auto_present(turn, ledger.store.artifact_dict(inspected)) is None
    assert d.listing(turn) == []

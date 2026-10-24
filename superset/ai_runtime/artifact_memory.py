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
"""Scoped retrieval of persisted chart baselines for follow-up requests."""

from __future__ import annotations

from typing import Any

from superset.ai_runtime import store
from superset.extensions import db
from superset.models.ai_runtime import AiRuntimeArtifact, AiRuntimeTurn


def _rows(turn: AiRuntimeTurn) -> Any:
    return (
        db.session.query(AiRuntimeArtifact)
        .join(AiRuntimeTurn, AiRuntimeArtifact.turn_id == AiRuntimeTurn.id)
        .filter(
            AiRuntimeTurn.session_id == turn.session_id,
            AiRuntimeTurn.user_id == turn.user_id,
            AiRuntimeTurn.post_id == turn.post_id,
            AiRuntimeArtifact.artifact_type == "chart",
        )
    )


def _authorize(artifact: dict[str, Any]) -> None:
    payload = artifact["payload"]
    chart_id = payload.get("slice_id")
    form_data = payload.get("form_data") or {}
    datasource = form_data.get("datasource") if isinstance(form_data, dict) else None
    refs = []
    if isinstance(chart_id, int):
        refs.append({"type": "chart", "id": chart_id})
    if isinstance(datasource, str) and datasource.endswith("__table"):
        try:
            refs.append({"type": "dataset", "id": int(datasource.split("__", 1)[0])})
        except ValueError:
            pass
    if not refs:
        raise store.RuntimeRequestError(
            "Chart baseline is unavailable", 403, "artifact_denied"
        )
    store.validate_context(refs)


def index(turn: AiRuntimeTurn) -> list[dict[str, Any]]:
    """Newest permitted chart references; payloads are fetched on demand."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in (
        _rows(turn)
        .order_by(AiRuntimeTurn.created_on.desc(), AiRuntimeArtifact.created_on.desc())
        .limit(32)
    ):
        artifact = store.artifact_dict(row)
        try:
            _authorize(artifact)
        except store.RuntimeRequestError:
            continue
        payload = artifact["payload"]
        identity = str(
            payload.get("form_data_key") or payload.get("slice_id") or artifact["id"]
        )
        current = grouped.get(identity)
        if current is None or artifact["version"] > current["version"]:
            grouped[identity] = {
                key: artifact[key] for key in ("id", "title", "version", "saved")
            }
    return list(grouped.values())[:8]


def find_preview(
    turn: AiRuntimeTurn, payload: dict[str, Any]
) -> AiRuntimeArtifact | None:
    """A metadata read of an unchanged preview is not a new chart version."""
    key = payload.get("form_data_key")
    if not key or not payload.get("form_data"):
        return None
    for row in _rows(turn).order_by(AiRuntimeArtifact.created_on.desc()).limit(32):
        previous = store.loads(row.payload_json)
        if (
            previous.get("form_data_key") == key
            and previous.get("form_data") == payload["form_data"]
        ):
            return row
    return None


def read(turn: AiRuntimeTurn, identifier: str | None = None) -> dict[str, Any]:
    """Resolve within the original actor/post/thread and check current BI access."""
    query = _rows(turn)
    if identifier is None:
        available = index(turn)
        identifier = available[0]["id"] if available else "unavailable"
    if identifier:
        query = query.filter(AiRuntimeArtifact.id == identifier)
    row = query.order_by(
        AiRuntimeTurn.created_on.desc(), AiRuntimeArtifact.created_on.desc()
    ).first()
    if row is None:
        raise store.RuntimeRequestError(
            "Chart artifact not found", 404, "artifact_not_found"
        )
    artifact = store.artifact_dict(row)
    _authorize(artifact)
    # A later get_chart_info may describe the same preview without carrying the
    # original creation config. Recover that config from its scoped producer.
    candidates = [row]
    key = artifact["payload"].get("form_data_key")
    if key:
        candidates += [
            candidate
            for candidate in _rows(turn)
            .order_by(AiRuntimeArtifact.created_on.desc())
            .limit(32)
            if candidate.id != row.id
            and store.loads(candidate.payload_json).get("form_data_key") == key
        ]
    body: dict[str, Any] = {}
    for candidate in candidates:
        producer = db.session.query(AiRuntimeTurn).get(candidate.turn_id)
        state = store.loads(producer.state_json)
        call_id = store.loads(candidate.provenance_json).get("call_id")
        operation = state.get("checkpoint", {}).get("calls", {}).get(call_id, {})
        args = operation.get("arguments", {})
        candidate_body = args.get("request", args)
        if not body or candidate_body.get("config"):
            body = candidate_body
        if body.get("config"):
            break
    artifact["source_request"] = {
        key: body[key]
        for key in (
            "dataset_id",
            "config",
            "identifier",
            "form_data_key",
            "save_chart",
            "generate_preview",
        )
        if key in body
    }
    return artifact


def hydrate_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Use native cache access checks to normalize an existing preview response."""
    if payload.get("form_data") or not payload.get("form_data_key"):
        return payload
    from superset.commands.explore.form_data.get import GetFormDataCommand
    from superset.commands.explore.form_data.parameters import CommandParameters

    raw = GetFormDataCommand(CommandParameters(key=payload["form_data_key"])).run()
    form_data = store.loads(raw) if isinstance(raw, str) else raw
    if isinstance(form_data, dict):
        return {
            **payload,
            "form_data": form_data,
            "viz_type": payload.get("viz_type") or form_data.get("viz_type"),
        }
    return payload

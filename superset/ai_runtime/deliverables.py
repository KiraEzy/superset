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
"""Append-only presentation registrations over immutable conversation artifacts."""

from __future__ import annotations

import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from superset import security_manager
from superset.extensions import db
from superset.models.ai_runtime import AiRuntimeArtifact, AiRuntimeItem, AiRuntimeTurn
from superset.utils import json

from . import artifact_memory, store


def rows(turn: AiRuntimeTurn) -> Any:
    """Restrict every resolution to the original conversation and actor/post."""
    return (
        db.session.query(AiRuntimeArtifact)
        .join(AiRuntimeTurn, AiRuntimeArtifact.turn_id == AiRuntimeTurn.id)
        .filter(
            AiRuntimeTurn.session_id == turn.session_id,
            AiRuntimeTurn.user_id == turn.user_id,
            AiRuntimeTurn.post_id == turn.post_id,
        )
    )


def resource_key(artifact: dict[str, Any]) -> str | None:
    """Only confirmed saved BI identities can be automatically presented."""
    kind, payload = artifact["type"], artifact["payload"]
    connection = artifact.get("provenance", {}).get("connection_id")
    identifier = payload.get("slice_id", payload.get("id"))
    if kind not in {"chart", "dashboard"} or not connection:
        return None
    if (
        isinstance(identifier, bool)
        or not isinstance(identifier, int)
        or identifier <= 0
    ):
        return None
    if not artifact["saved"] or (
        payload.get("form_data_key") and payload.get("saved") is False
    ):
        return None
    return json.dumps([connection, kind, str(identifier)], separators=(",", ":"))


def authorize(artifact: dict[str, Any]) -> None:
    """Recheck native resource/database access before presenting or displaying."""
    kind, payload = artifact["type"], artifact["payload"]
    if artifact.get("provenance", {}).get("connection_id") != "focalbi":
        raise store.RuntimeRequestError(
            "Visualization is unavailable", 403, "deliverable_denied"
        )
    if kind == "chart":
        artifact_memory._authorize(artifact)  # Reuse chart and dataset authorization.
        form_data = payload.get("form_data")
        form_data = form_data if isinstance(form_data, dict) else {}
        if not (payload.get("viz_type") or form_data.get("viz_type")):
            raise store.RuntimeRequestError("Chart is not ready to display")
    elif kind == "dashboard":
        store.validate_context([{"type": "dashboard", "id": payload.get("id")}])
    elif kind == "table" and isinstance(payload.get("rows"), list):
        source = payload.get("source_request", {})
        if isinstance(source.get("dataset_id"), int):
            store.validate_context([{"type": "dataset", "id": source["dataset_id"]}])
        elif isinstance(source.get("database_id"), int):
            from superset.models.core import Database

            database = db.session.query(Database).get(source["database_id"])
            if not database or not security_manager.can_access_database(database):
                raise store.RuntimeRequestError(
                    "Result is unavailable", 403, "deliverable_denied"
                )
        else:
            raise store.RuntimeRequestError(
                "Result authorization is unavailable", 403, "deliverable_denied"
            )
    else:
        raise store.RuntimeRequestError("This artifact has no supported visualization")


def completed(row: AiRuntimeArtifact) -> bool:
    """An unfinished or failed source operation cannot publish a result."""
    source = db.session.query(AiRuntimeTurn).get(row.turn_id)
    call = store.loads(row.provenance_json).get("call_id")
    record = (
        store.loads(source.state_json)
        .get("checkpoint", {})
        .get("calls", {})
        .get(call, {})
    )
    result = record.get("result") or {}
    structured = result.get("structuredContent")
    structured = structured if isinstance(structured, dict) else {}
    return bool(
        record.get("status") == "completed"
        and not result.get("isError")
        and structured.get("success") is not False
    )


def descriptor(artifact: dict[str, Any], key: str, title: str) -> dict[str, Any]:
    """Public presentation metadata contains no raw evidence or credentials."""
    try:
        authorize(artifact)
        available = True
    except (store.RuntimeRequestError, ValueError, TypeError):
        available = False
    return {
        "key": key,
        "artifact_id": artifact["id"],
        "title": title,
        "type": artifact["type"],
        "saved": bool(resource_key(artifact)),
        "version": artifact["version"],
        "available": available,
    }


def registrations(turn: AiRuntimeTurn) -> list[AiRuntimeItem]:
    """Load the scoped append-only presentation ledger in publication order."""
    return (
        db.session.query(AiRuntimeItem)
        .join(AiRuntimeTurn)
        .filter(
            AiRuntimeTurn.session_id == turn.session_id,
            AiRuntimeTurn.user_id == turn.user_id,
            AiRuntimeTurn.post_id == turn.post_id,
            AiRuntimeItem.kind == "deliverable",
        )
        .order_by(AiRuntimeItem.created_on, AiRuntimeItem.id)
        .all()
    )


def removed_chart_keys(item: AiRuntimeItem) -> list[str]:
    """Only successful, explicit native dashboard removals retire presentation."""
    payload = store.loads(item.payload_json)
    if (
        item.kind != "tool"
        or item.status != "completed"
        or not re.fullmatch(
            r"(?:focalbi__)?configure_dashboard(?:_[0-9a-f]{10})?",
            str(payload.get("tool", "")),
        )
    ):
        return []
    result = payload.get("result") or {}
    structured = result.get("structuredContent") or {}
    if result.get("isError") or (
        isinstance(structured, dict) and structured.get("success") is False
    ):
        return []
    arguments = payload.get("arguments") or {}
    body = arguments.get("request", arguments)
    removed = body.get("remove_chart_ids") or []
    return (
        [
            json.dumps(["focalbi", "chart", str(identifier)], separators=(",", ":"))
            for identifier in removed
            if isinstance(identifier, int)
            and not isinstance(identifier, bool)
            and identifier > 0
        ]
        if isinstance(removed, list)
        else []
    )


def listing(turn: AiRuntimeTurn) -> list[dict[str, Any]]:
    """Project legacy saved resources and explicit publications without mutation."""
    sources = [
        row
        for row in rows(turn).order_by(
            AiRuntimeTurn.created_on, AiRuntimeArtifact.created_on, AiRuntimeArtifact.id
        )
        if completed(row)
    ]
    artifacts = {row.id: store.artifact_dict(row) for row in sources}
    operations = (
        db.session.query(AiRuntimeItem)
        .join(AiRuntimeTurn)
        .filter(
            AiRuntimeTurn.session_id == turn.session_id,
            AiRuntimeTurn.user_id == turn.user_id,
            AiRuntimeTurn.post_id == turn.post_id,
            AiRuntimeItem.kind == "tool",
        )
        .all()
    )
    timeline: list[tuple[Any, int, Any]] = [(row.created_on, 1, row) for row in sources]
    timeline += [
        (item.created_on, 0, item) for item in operations if removed_chart_keys(item)
    ]
    timeline.sort(key=lambda value: (value[0], value[1]))
    selected: dict[str, dict[str, Any]] = {}
    retired: dict[str, Any] = {}
    for timestamp, kind, row in timeline:
        if kind == 0:
            for key in removed_chart_keys(row):
                selected.pop(key, None)
                retired[key] = timestamp
            continue
        artifact = artifacts[row.id]
        key = resource_key(artifact)
        if key:
            if (
                not artifact["payload"].get("saved", artifact["saved"])
                and key not in selected
            ):
                continue
            if key in retired and not artifact["payload"].get("saved"):
                continue
            retired.pop(key, None)
            selected.pop(key, None)
            selected[key] = descriptor(artifact, key, artifact["title"])
    _apply_publications(turn, artifacts, selected, retired)
    return list(selected.values())


def _apply_publications(
    turn: AiRuntimeTurn,
    artifacts: dict[str, dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    retired: dict[str, Any],
) -> None:
    for item in registrations(turn):
        value = store.loads(item.payload_json)
        artifact = artifacts.get(value.get("artifact_id"))
        if artifact:
            key = value["key"]
            if resource_key(artifact) and str(item.external_id or "").startswith(
                "auto:"
            ):
                # Automatic entries follow the chronological resource projection.
                continue
            if key in retired and (
                str(item.external_id or "").startswith("auto:")
                or item.created_on <= retired[key]
            ):
                continue
            # Saved resources retain their latest snapshot.
            if resource_key(artifact) and key in selected:
                continue
            selected[key] = descriptor(artifact, key, value["title"])


def present(
    turn: AiRuntimeTurn, args: dict[str, Any], operation_id: str | None = None
) -> dict[str, Any]:
    """Validate and append an idempotent registration; caller owns transaction/lease."""
    row = rows(turn).filter(AiRuntimeArtifact.id == args.get("artifact_id")).first()
    title = args.get("title")
    if row is None or not completed(row):
        raise store.RuntimeRequestError(
            "Completed artifact not found", 404, "deliverable_unavailable"
        )
    if not isinstance(title, str) or not title.strip() or len(title) > 256:
        raise store.RuntimeRequestError("A deliverable title is required")
    artifact = store.artifact_dict(row)
    authorize(artifact)
    key = resource_key(artifact) or f"visual:{row.id}"
    replacement = args.get("replaces_artifact_id")
    if replacement:
        prior = next(
            (value for value in listing(turn) if value["artifact_id"] == replacement),
            None,
        )
        if not prior or prior["type"] != artifact["type"]:
            raise store.RuntimeRequestError(
                "Replacement must be a presented artifact of the same type"
            )
        if prior["saved"] and not resource_key(artifact):
            raise store.RuntimeRequestError(
                "Present an unsaved preview separately from its saved resource"
            )
        # Distinct saved resources remain distinct even when their titles match.
        if resource_key(artifact) and key != prior["key"]:
            raise store.RuntimeRequestError(
                "Different saved resources cannot replace each other"
            )
        if not prior["available"]:
            raise store.RuntimeRequestError(
                "Replacement is unavailable", 403, "deliverable_denied"
            )
        key = prior["key"]
    value = descriptor(artifact, key, title.strip())
    identifier = str(
        uuid5(
            NAMESPACE_URL,
            f"{turn.id}:deliverable:{operation_id or store.dumps(value)}",
        )
    )
    existing = db.session.query(AiRuntimeItem).get(identifier)
    if existing is not None and store.loads(existing.payload_json) != value:
        raise store.RuntimeRequestError("Presentation changed while replaying")
    if existing is None:
        db.session.add(
            AiRuntimeItem(
                id=identifier,
                turn_id=turn.id,
                kind="deliverable",
                external_id=operation_id,
                payload_json=store.dumps(value),
            )
        )
        db.session.flush()
    return value


def auto_present(
    turn: AiRuntimeTurn, artifact: dict[str, Any]
) -> dict[str, Any] | None:
    """Register successful saved resources; retain other evidence separately."""
    key = resource_key(artifact)
    if not key:
        return None
    try:
        if artifact["payload"].get("saved") is False:
            current = next(
                (entry for entry in listing(turn) if entry["key"] == key), None
            )
            return (
                current
                if current and current["artifact_id"] == artifact["id"]
                else None
            )
        value = present(
            turn,
            {"artifact_id": artifact["id"], "title": artifact["title"]},
            operation_id=f"auto:{artifact['id']}",
        )
        current = next(
            (entry for entry in listing(turn) if entry["key"] == value["key"]), None
        )
        return current if current and current["artifact_id"] == artifact["id"] else None
    except (store.RuntimeRequestError, ValueError, TypeError):
        return None


def references(turn: AiRuntimeTurn, call_id: str | None = None) -> list[dict[str, Any]]:
    """Expose persisted IDs for successful renderable outputs to the model."""
    result = []
    for row in rows(turn).order_by(AiRuntimeArtifact.created_on.desc()).limit(100):
        artifact = store.artifact_dict(row)
        if (
            call_id is not None
            and artifact.get("provenance", {}).get("call_id") != call_id
        ):
            continue
        if artifact["type"] not in {"chart", "dashboard", "table"} or not completed(
            row
        ):
            continue
        try:
            authorize(artifact)
        except (store.RuntimeRequestError, ValueError, TypeError):
            continue
        result.append(
            {
                "artifact_id": row.id,
                "type": artifact["type"],
                "title": artifact["title"],
            }
        )
    return result

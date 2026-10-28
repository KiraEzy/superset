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
"""Offline, manifest-bound conversation reset; never reset BI or connection tables."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from sqlalchemy import inspect, MetaData, select, Table, text

from superset.utils import json

# Delete children first. Images live in this table, not in filesystem paths.
CONVERSATION_TABLES = (
    "ai_runtime_event",
    "ai_runtime_item",
    "ai_runtime_artifact",
    "ai_runtime_outbox",
    "ai_runtime_turn",
    "ai_chat_message",
    "ai_sdk_summary",
    "ai_sdk_item",
    "ai_sdk_session",
    "ai_chat_image",
    "ai_chat_session",
)
PROTECTED_TABLES = (
    "ai_connection_config",
    "ai_model_connection",
    "ai_model",
    "ai_model_verification",
    "ai_runtime_connection",
    "ai_runtime_account",
    "ai_runtime_oauth_state",
    "dbs",
    "tables",
    "table_columns",
    "sql_metrics",
    "slices",
    "dashboards",
    "dashboard_slices",
    "ab_user",
    "ab_role",
    "ab_user_role",
    "ab_permission_view_role",
)


def _encode(value: Any) -> Any:
    if isinstance(value, (bytes, memoryview)):
        return {"binary": base64.b64encode(bytes(value)).decode()}
    return str(value)


def fingerprint(connection: Any, table: Table) -> dict[str, Any]:
    """Hash raw persisted values without decoding encrypted connection secrets."""
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(select(table).order_by(*table.primary_key.columns)):
        digest.update(
            json.dumps(dict(row._mapping), sort_keys=True, default=_encode).encode()
        )
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def inventory(connection: Any) -> dict[str, Any]:
    """Capture exact conversation/protected state and reject unknown inbound FKs."""
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    selected = set(CONVERSATION_TABLES) & present
    for name in present - selected:
        if any(
            fk["referred_table"] in selected for fk in inspector.get_foreign_keys(name)
        ):
            raise ValueError("Unreviewed conversation foreign key: " + name)
    metadata = MetaData()

    def capture(names: Any) -> dict[str, Any]:
        return {
            name: fingerprint(
                connection, Table(name, metadata, autoload_with=connection)
            )
            for name in names
            if name in present
        }

    return {
        "schema_version": 1,
        "conversations": capture(CONVERSATION_TABLES),
        "protected": capture(PROTECTED_TABLES),
    }


def reset(connection: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    """Verify the frozen inventory, delete only captured chat tables, verify BI state.

    The caller owns the transaction and must stop submissions/workers first.
    PostgreSQL locks prevent changes between manifest comparison and deletion.
    """
    present = set(inspect(connection).get_table_names())
    selected = [name for name in CONVERSATION_TABLES if name in present]
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "LOCK TABLE "
                + ", ".join('"' + n + '"' for n in selected)
                + " IN ACCESS EXCLUSIVE MODE"
            )
        )
    before = inventory(connection)
    if before != manifest:
        raise ValueError("Reset inventory changed; capture and review a new manifest")
    for name in selected:
        connection.execute(Table(name, MetaData(), autoload_with=connection).delete())
    after = inventory(connection)
    if after["protected"] != before["protected"]:
        raise ValueError("Protected data changed; rolling back conversation reset")
    if any(row["count"] for row in after["conversations"].values()):
        raise ValueError("Conversation reset is incomplete")
    return after

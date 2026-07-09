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
from __future__ import annotations

from typing import Any

from flask_login import current_user

from superset.extensions import db
from superset.global_configuration.registry import (
    KNOWN_KEYS,
    deserialize_stored,
    is_public,
    parse_and_validate,
    serialize_value,
)
from superset.models.global_configuration import GlobalConfiguration


def _user_id() -> int | None:
    try:
        return current_user.get_id() and int(current_user.get_id())
    except Exception:  # noqa: BLE001
        return None


def get_all_rows() -> list[GlobalConfiguration]:
    return (
        db.session.query(GlobalConfiguration)
        .order_by(GlobalConfiguration.key.asc())
        .all()
    )


def get_row(key: str) -> GlobalConfiguration | None:
    return (
        db.session.query(GlobalConfiguration)
        .filter_by(key=key)
        .one_or_none()
    )


def effective_known_map() -> dict[str, Any]:
    rows = {row.key: row.value for row in get_all_rows()}
    result: dict[str, Any] = {}
    for key, meta in KNOWN_KEYS.items():
        if key in rows:
            result[key] = deserialize_stored(key, rows[key])
        else:
            result[key] = meta.default
    return result


def public_map() -> dict[str, Any]:
    known = effective_known_map()
    return {k: v for k, v in known.items() if is_public(k)}


def upsert_entries(entries: dict[str, Any]) -> dict[str, Any]:
    """Validate and upsert; returns effective known map after write."""
    for key, raw in entries.items():
        value = parse_and_validate(key, raw)
        stored = serialize_value(key, value) if key in KNOWN_KEYS else str(value)
        row = get_row(key)
        if row is None:
            row = GlobalConfiguration(key=key, value=stored)
            db.session.add(row)
        else:
            row.value = stored
    db.session.commit()
    return effective_known_map()


def delete_key(key: str) -> None:
    row = get_row(key)
    if row is None:
        return
    db.session.delete(row)
    db.session.commit()

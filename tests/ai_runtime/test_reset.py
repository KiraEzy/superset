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
"""Offline cutover deletes only exact captured conversations and rolls back drift."""

from typing import Any

import pytest
from sqlalchemy import (
    Column,
    create_engine,
    ForeignKey,
    Integer,
    MetaData,
    select,
    Table,
)

from superset.ai_runtime.reset import CONVERSATION_TABLES, inventory, reset


@pytest.fixture
def database() -> Any:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for name in (*CONVERSATION_TABLES, "slices", "ai_model_connection"):
        Table(name, metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        for table in metadata.tables.values():
            connection.execute(table.insert().values(id=1))
    yield engine, metadata
    engine.dispose()


def test_reset_preserves_bi_and_connections(database: Any) -> None:
    engine, metadata = database
    with engine.begin() as connection:
        captured = inventory(connection)
        result = reset(connection, captured)
        assert all(row["count"] == 0 for row in result["conversations"].values())
        assert result["protected"] == captured["protected"]


@pytest.mark.parametrize("changed", ["ai_chat_session", "ai_model_connection"])
def test_stale_manifest_cannot_delete_new_or_changed_data(
    database: Any, changed: str
) -> None:
    engine, metadata = database
    with engine.begin() as connection:
        captured = inventory(connection)
        connection.execute(metadata.tables[changed].insert().values(id=2))
        with pytest.raises(ValueError, match="inventory changed"):
            reset(connection, captured)
        assert (
            connection.execute(select(metadata.tables["ai_chat_session"])).first()
            is not None
        )


def test_unknown_inbound_foreign_key_requires_review(database: Any) -> None:
    engine, metadata = database
    Table(
        "unreviewed",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("chat_id", Integer, ForeignKey("ai_chat_session.id")),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        with pytest.raises(ValueError, match="Unreviewed conversation foreign key"):
            inventory(connection)

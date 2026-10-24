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
"""Verify additive schema migration and rollback on an isolated database."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_migration_preserves_legacy_rows_and_connection_settings():
    import superset

    path = (
        Path(superset.__file__).parent
        / "migrations/versions/2026-10-20_12-00_f1a2b3c4d5e6_durable_ai_chat.py"
    )
    spec = importlib.util.spec_from_file_location("runtime_migration_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE ai_chat_session (id INTEGER PRIMARY KEY, title VARCHAR(256))"
            )
        )
        connection.execute(
            sa.text("INSERT INTO ai_chat_session VALUES (1, 'legacy test')")
        )
        connection.execute(sa.text("CREATE TABLE ab_user (id INTEGER PRIMARY KEY)"))
        connection.execute(
            sa.text(
                "CREATE TABLE ai_connection_config (id INTEGER PRIMARY KEY, config BLOB)"
            )
        )
        connection.execute(
            sa.text("INSERT INTO ai_connection_config VALUES (1, 'unchanged')")
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert (
            connection.execute(
                sa.text("SELECT runtime_version FROM ai_chat_session WHERE id=1")
            ).scalar()
            == 1
        )
        assert (
            len(
                [
                    name
                    for name in sa.inspect(connection).get_table_names()
                    if name.startswith("ai_runtime_")
                ]
            )
            == 8
        )
        assert (
            connection.execute(
                sa.text("SELECT config FROM ai_connection_config WHERE id=1")
            ).scalar()
            == "unchanged"
        )
        migration.downgrade()
        assert (
            connection.execute(
                sa.text("SELECT title FROM ai_chat_session WHERE id=1")
            ).scalar()
            == "legacy test"
        )
        assert not any(
            name.startswith("ai_runtime_")
            for name in sa.inspect(connection).get_table_names()
        )

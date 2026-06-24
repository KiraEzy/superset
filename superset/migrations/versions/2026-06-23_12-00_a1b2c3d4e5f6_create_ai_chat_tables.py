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
"""create_ai_chat_tables

Revision ID: a1b2c3d4e5f6
Revises: 4b2a8c9d3e1f
Create Date: 2026-06-23 12:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy_utils import UUIDType

from superset.migrations.shared.utils import (
    create_fks_for_table,
    create_index,
    create_table,
    drop_fks_for_table,
    drop_index,
    drop_table,
)

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "4b2a8c9d3e1f"


def upgrade():
    create_table(
        "ai_chat_session",
        sa.Column("uuid", UUIDType(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("changed_on", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("created_by_fk", sa.Integer(), nullable=True),
        sa.Column("changed_by_fk", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    create_fks_for_table(
        "fk_ai_chat_session_created_by_fk_ab_user",
        "ai_chat_session",
        "ab_user",
        ["created_by_fk"],
        ["id"],
    )

    create_fks_for_table(
        "fk_ai_chat_session_changed_by_fk_ab_user",
        "ai_chat_session",
        "ab_user",
        ["changed_by_fk"],
        ["id"],
    )

    create_index("ai_chat_session", "ix_ai_chat_session_changed_on", ["changed_on"])

    create_table(
        "ai_chat_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "content",
            sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"),
            nullable=False,
        ),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    create_fks_for_table(
        "fk_ai_chat_message_session_id_ai_chat_session",
        "ai_chat_message",
        "ai_chat_session",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )

    create_index(
        "ai_chat_message",
        "ix_ai_chat_message_session_id_created_on",
        ["session_id", "created_on"],
    )


def downgrade():
    drop_index("ai_chat_message", "ix_ai_chat_message_session_id_created_on")
    drop_fks_for_table(
        "fk_ai_chat_message_session_id_ai_chat_session",
        "ai_chat_message",
    )
    drop_table("ai_chat_message")

    drop_index("ai_chat_session", "ix_ai_chat_session_changed_on")
    drop_fks_for_table("fk_ai_chat_session_changed_by_fk_ab_user", "ai_chat_session")
    drop_fks_for_table("fk_ai_chat_session_created_by_fk_ab_user", "ai_chat_session")
    drop_table("ai_chat_session")

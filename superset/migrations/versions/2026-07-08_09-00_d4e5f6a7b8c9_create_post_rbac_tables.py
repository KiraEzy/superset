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
"""create_post_rbac_tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-08 09:00:00.000000

"""

import sqlalchemy as sa

from superset.migrations.shared.utils import (
    create_fks_for_table,
    create_index,
    create_table,
    drop_index,
    drop_table,
)

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"


def upgrade():
    create_table(
        "ab_post",
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("changed_on", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=150), nullable=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_fk", sa.Integer(), nullable=True),
        sa.Column("changed_by_fk", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    create_fks_for_table(
        "fk_ab_post_created_by_fk_ab_user",
        "ab_post",
        "ab_user",
        ["created_by_fk"],
        ["id"],
    )
    create_fks_for_table(
        "fk_ab_post_changed_by_fk_ab_user",
        "ab_post",
        "ab_user",
        ["changed_by_fk"],
        ["id"],
    )

    create_table(
        "ab_user_post",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("last_used_on", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "post_id", name="uq_ab_user_post_user_post"),
    )
    create_fks_for_table(
        "fk_ab_user_post_user_id_ab_user",
        "ab_user_post",
        "ab_user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    create_fks_for_table(
        "fk_ab_user_post_post_id_ab_post",
        "ab_user_post",
        "ab_post",
        ["post_id"],
        ["id"],
        ondelete="CASCADE",
    )
    create_index("ab_user_post", "ix_ab_user_post_user_id", ["user_id"])

    create_table(
        "ab_post_role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "role_id", name="uq_ab_post_role_post_role"),
    )
    create_fks_for_table(
        "fk_ab_post_role_post_id_ab_post",
        "ab_post_role",
        "ab_post",
        ["post_id"],
        ["id"],
        ondelete="CASCADE",
    )
    create_fks_for_table(
        "fk_ab_post_role_role_id_ab_role",
        "ab_post_role",
        "ab_role",
        ["role_id"],
        ["id"],
        ondelete="CASCADE",
    )
    create_index("ab_post_role", "ix_ab_post_role_post_id", ["post_id"])


def downgrade():
    # drop_table() drops the table's own foreign key constraints before dropping
    # the table, so explicit drop_fks_for_table calls are not required here.
    drop_index("ab_post_role", "ix_ab_post_role_post_id")
    drop_table("ab_post_role")

    drop_index("ab_user_post", "ix_ab_user_post_user_id")
    drop_table("ab_user_post")

    drop_table("ab_post")

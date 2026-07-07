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
"""create_ai_connection_config

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-06 12:00:00.000000

"""

import sqlalchemy as sa

from superset.migrations.shared.utils import (
    create_fks_for_table,
    create_table,
    drop_fks_for_table,
    drop_table,
)

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"


def upgrade():
    create_table(
        "ai_connection_config",
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("changed_on", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config", sa.LargeBinary(), nullable=True),
        sa.Column("created_by_fk", sa.Integer(), nullable=True),
        sa.Column("changed_by_fk", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    create_fks_for_table(
        "fk_ai_connection_config_created_by_fk_ab_user",
        "ai_connection_config",
        "ab_user",
        ["created_by_fk"],
        ["id"],
    )

    create_fks_for_table(
        "fk_ai_connection_config_changed_by_fk_ab_user",
        "ai_connection_config",
        "ab_user",
        ["changed_by_fk"],
        ["id"],
    )


def downgrade():
    drop_fks_for_table(
        "fk_ai_connection_config_changed_by_fk_ab_user", "ai_connection_config"
    )
    drop_fks_for_table(
        "fk_ai_connection_config_created_by_fk_ab_user", "ai_connection_config"
    )
    drop_table("ai_connection_config")

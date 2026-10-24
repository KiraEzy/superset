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
"""Add model catalogue and private image storage.
Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Chat-only tables; no external service or MCP changes."""
    op.create_table(
        "ai_model_connection",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.LargeBinary(), nullable=False),
    )
    op.create_table(
        "ai_model",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("ai_model_connection.id"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(256), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("vision", sa.Boolean(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer()),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("connection_id", "model_name"),
    )
    op.create_table(
        "ai_model_verification",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("candidate_json", sa.LargeBinary(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("model_id", sa.String(36)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_on", sa.DateTime(), nullable=False),
        sa.Column("started_on", sa.DateTime()),
    )
    op.create_table(
        "ai_chat_image",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("ab_user.id"), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(128), nullable=False),
        sa.Column("mime", sa.String(32), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("bound", sa.Boolean(), nullable=False),
        sa.Column("created_on", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Remove only Chat model/image tables."""
    for name in (
        "ai_chat_image",
        "ai_model_verification",
        "ai_model",
        "ai_model_connection",
    ):
        op.drop_table(name)

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
"""Add the Chat-only durable runtime ledger; no conversation deletion.

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(36), primary_key=True)


def _turn() -> sa.Column:
    return sa.Column(
        "turn_id",
        sa.String(36),
        sa.ForeignKey("ai_runtime_turn.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _time() -> sa.Column:
    return sa.Column("created_on", sa.DateTime(), nullable=False)


def upgrade() -> None:
    """Additive schema only; rollout and legacy purge are separate operations."""
    with op.batch_alter_table("ai_chat_session") as batch:
        batch.add_column(
            sa.Column(
                "runtime_version", sa.Integer(), nullable=False, server_default="1"
            )
        )
        batch.add_column(sa.Column("post_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "profile_id", sa.String(64), nullable=False, server_default="default"
            )
        )
        batch.add_column(sa.Column("parent_uuid", sa.String(36), nullable=True))
        batch.create_index("ix_ai_chat_session_post_id", ["post_id"])
    op.create_table(
        "ai_runtime_turn",
        _id(),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("ai_chat_session.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("ab_user.id"), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("active_key", sa.String(36), unique=True),
        sa.Column("status", sa.String(24), nullable=False, index=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("state_json", sa.LargeBinary(), nullable=False),
        sa.Column("error_json", sa.Text()),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(36)),
        sa.Column("lease_expires", sa.DateTime(), index=True),
        _time(),
        sa.Column("changed_on", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "session_id", "idempotency_key", name="uq_ai_runtime_turn_submission"
        ),
    )
    op.create_table(
        "ai_runtime_item",
        _id(),
        _turn(),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("external_id", sa.String(256)),
        sa.Column("payload_json", sa.LargeBinary(), nullable=False),
        _time(),
    )
    op.create_table(
        "ai_runtime_event",
        _id(),
        _turn(),
        sa.Column("item_id", sa.String(36)),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.LargeBinary(), nullable=False),
        _time(),
        sa.UniqueConstraint("turn_id", "sequence", name="uq_ai_runtime_event_sequence"),
    )
    op.create_table(
        "ai_runtime_artifact",
        _id(),
        _turn(),
        sa.Column("artifact_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.LargeBinary(), nullable=False),
        sa.Column("provenance_json", sa.LargeBinary(), nullable=False),
        _time(),
    )
    op.create_table(
        "ai_runtime_outbox",
        _id(),
        _turn(),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        _time(),
        sa.Column("dispatched_on", sa.DateTime()),
    )
    op.create_table(
        "ai_runtime_connection",
        _id(),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("auth_type", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("allow_private", sa.Boolean(), nullable=False),
        sa.Column("reviewed_tools", sa.Text(), nullable=False),
        sa.Column("oauth_config", sa.LargeBinary()),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "ai_runtime_account",
        _id(),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("ai_runtime_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("ab_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("credentials", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint(
            "connection_id", "user_id", "post_id", name="uq_ai_runtime_account_scope"
        ),
    )
    op.create_table(
        "ai_runtime_oauth_state",
        sa.Column("state", sa.String(64), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("ai_runtime_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("ab_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("verifier", sa.LargeBinary(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("expires_on", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Drop only runtime-owned schema; production rollback normally keeps records."""
    for table in (
        "ai_runtime_oauth_state",
        "ai_runtime_account",
        "ai_runtime_connection",
        "ai_runtime_outbox",
        "ai_runtime_artifact",
        "ai_runtime_event",
        "ai_runtime_item",
        "ai_runtime_turn",
    ):
        op.drop_table(table)
    with op.batch_alter_table("ai_chat_session") as batch:
        batch.drop_index("ix_ai_chat_session_post_id")
        for column in ("parent_uuid", "profile_id", "post_id", "runtime_version"):
            batch.drop_column(column)

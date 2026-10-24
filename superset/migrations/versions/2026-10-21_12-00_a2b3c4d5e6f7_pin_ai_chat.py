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
"""Persist conversation pins.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Existing conversations start unpinned."""
    with op.batch_alter_table("ai_chat_session") as batch:
        batch.add_column(
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Remove pin metadata without deleting conversations."""
    with op.batch_alter_table("ai_chat_session") as batch:
        batch.drop_column("is_pinned")

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
"""Normalize binary encrypted Chat columns after early catalogue installation.
Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve encrypted payloads using the native encrypted field storage type."""
    bind = op.get_bind()
    for table, column in (
        ("ai_model_connection", "config_json"),
        ("ai_model_verification", "candidate_json"),
        ("ai_chat_image", "data"),
    ):
        info = next(
            c for c in sa.inspect(bind).get_columns(table) if c["name"] == column
        )
        if isinstance(info["type"], sa.LargeBinary):
            continue
        if bind.dialect.name == "postgresql":
            op.alter_column(
                table,
                column,
                type_=sa.LargeBinary(),
                postgresql_using=f"{column}::bytea",
            )
        else:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(
                    column, type_=sa.LargeBinary(), existing_type=info["type"]
                )


def downgrade() -> None:
    """Binary encrypted columns are also valid for the preceding revision."""

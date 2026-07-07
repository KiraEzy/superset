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
"""alter_ai_connection_config_config_to_bytea

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-07 08:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"


def upgrade():
    with op.batch_alter_table("ai_connection_config") as batch_op:
        try:
            batch_op.alter_column(
                "config",
                existing_type=sa.Text(),
                type_=sa.LargeBinary(),
                postgresql_using="config::bytea",
                existing_nullable=True,
            )
        except TypeError:
            batch_op.alter_column(
                "config",
                existing_type=sa.Text(),
                type_=sa.LargeBinary(),
                existing_nullable=True,
            )


def downgrade():
    with op.batch_alter_table("ai_connection_config") as batch_op:
        batch_op.alter_column(
            "config",
            existing_type=sa.LargeBinary(),
            type_=sa.Text(),
            existing_nullable=True,
        )

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
"""Move configured model token budgets into the model catalogue.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
"""

import sqlalchemy as sa
from alembic import op
from flask import current_app

from superset.utils import json

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Copy legacy profiles once, leaving connections and history untouched."""
    op.add_column(
        "ai_model",
        sa.Column(
            "runtime_settings_json", sa.Text(), nullable=True, server_default="{}"
        ),
    )
    op.add_column(
        "ai_model",
        sa.Column(
            "settings_revision", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    models = sa.table(
        "ai_model",
        sa.column("model_name", sa.String()),
        sa.column("runtime_settings_json", sa.Text()),
    )
    fields = {
        "context_window_tokens",
        "response_tokens",
        "tool_result_tokens",
        "context_chars",
    }
    for name, profile in current_app.config.get(
        "AI_RUNTIME_MODEL_CONTEXT_LIMITS", {}
    ).items():
        saved = {key: value for key, value in profile.items() if key in fields}
        op.get_bind().execute(
            models.update()
            .where(models.c.model_name == name)
            .values(runtime_settings_json=json.dumps(saved))
        )


def downgrade() -> None:
    """Drop database model budgets; retain all model identities and connections."""
    op.drop_column("ai_model", "settings_revision")
    op.drop_column("ai_model", "runtime_settings_json")

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
"""Database-owned token budgets scoped to a connection's model identity."""

from typing import Any

from superset.ai_runtime import settings
from superset.extensions import db
from superset.models.ai_model_catalog import AiModel
from superset.utils import json

TOKEN_FIELDS = ("context_window_tokens", "response_tokens", "tool_result_tokens")
MAX_TOKENS = 100_000_000
MIN_INPUT_TOKENS = 1024


class ModelSettingsConflictError(ValueError):
    """A stale administrator form must reload before saving."""


def overrides(model: AiModel) -> dict[str, Any]:
    """Return only settings stored for this model; never consult Python overrides."""
    return json.loads(model.runtime_settings_json or "{}")


def describe(model: AiModel, connection: dict[str, Any]) -> dict[str, Any]:
    """Expose effective values and reset defaults without endpoint credentials."""
    defaults = settings.limits(
        model.model_name, {**connection, "model_runtime_settings": {}}
    )
    effective = settings.limits(
        model.model_name, {**connection, "model_runtime_settings": overrides(model)}
    )
    values = {key: effective[key] for key in TOKEN_FIELDS}
    return {
        "values": values,
        "defaults": {key: defaults[key] for key in TOKEN_FIELDS},
        "revision": model.settings_revision,
        "input_allowance_tokens": values["context_window_tokens"]
        - values["response_tokens"]
        - values["tool_result_tokens"],
    }


def _validate(data: Any) -> tuple[int, dict[str, Any] | None]:
    """Reject incomplete, fractional and unusable input budgets."""
    if not isinstance(data, dict) or set(data) - {"values", "revision", "reset"}:
        raise ValueError("Provide model settings, revision and optional reset")
    revision = data.get("revision")
    if type(revision) is not int or revision < 0:
        raise ValueError("A valid settings revision is required")
    reset = data.get("reset", False)
    if type(reset) is not bool:
        raise ValueError("Reset must be a boolean")
    if reset:
        if "values" in data:
            raise ValueError("Reset cannot include custom values")
        return revision, None
    values = data.get("values")
    if not isinstance(values, dict) or set(values) != set(TOKEN_FIELDS):
        raise ValueError("Provide context, response and tool-result token limits")
    if any(type(v) is not int or not 1 <= v <= MAX_TOKENS for v in values.values()):
        raise ValueError("Token limits must be whole numbers between 1 and 100000000")
    remaining = (
        values["context_window_tokens"]
        - values["response_tokens"]
        - values["tool_result_tokens"]
    )
    if remaining < MIN_INPUT_TOKENS:
        raise ValueError(
            "Leave at least 1024 tokens for model input after reservations"
        )
    return revision, values


def save(model_id: str, data: Any) -> None:
    """Validate a complete budget and atomically replace an expected revision."""
    revision, values = _validate(data)
    model = db.session.query(AiModel).get(model_id)
    if model is None:
        raise ValueError("Model not found")
    profile = {} if values is None else {**overrides(model), **values}
    changed = (
        db.session.query(AiModel)
        .filter_by(id=model_id, settings_revision=revision)
        .update(
            {
                "runtime_settings_json": json.dumps(profile),
                "settings_revision": revision + 1,
            },
            synchronize_session=False,
        )
    )
    if changed != 1:
        db.session.rollback()
        raise ModelSettingsConflictError(
            "Model settings changed. Reload the page before saving."
        )
    db.session.commit()

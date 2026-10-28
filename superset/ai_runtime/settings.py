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
"""Chat-only settings; importing these does not configure the MCP server."""

import os
from typing import Any
from urllib.parse import urlsplit

from flask import current_app


def enabled() -> bool:
    """Gate new conversations without changing the engine of existing threads."""
    value = current_app.config.get("AI_CHAT_RUNTIME_ENABLED")
    if value is None:
        value = os.environ.get("AI_CHAT_RUNTIME_ENABLED", "false")
    return value is True or str(value).lower() in {"1", "true", "yes"}


def execution_snapshot() -> dict[str, Any]:
    """Select new turns only; queued and interrupted turns keep their snapshot."""
    from .execution import SDK_VERSION

    return {
        "execution_engine": "sdk_native",
        "execution_version": 3,
        "execution_sdk_version": SDK_VERSION,
    }


def limits(
    model: str | None = None, provider: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return bounded operational defaults configurable on Chat processes."""
    config = provider or {}
    # Resolved catalogue identities carry a database-owned snapshot. The Python
    # profiles are only a migration source for pre-existing model identities.
    profiles = current_app.config.get("AI_RUNTIME_MODEL_CONTEXT_LIMITS", {})
    profile = config.get("model_runtime_settings")
    if profile is None:
        profile = profiles.get(model, {}) if model else {}
    endpoint = urlsplit(str(config.get("llmApiBaseUrl", "")))
    # Chat operational cap below the official V4 1M context window:
    # https://api-docs.deepseek.com/quick_start/pricing/
    # Never infer this capacity for a similarly named self-hosted model.
    official_deepseek = (
        endpoint.scheme == "https"
        and endpoint.hostname == "api.deepseek.com"
        and endpoint.port in {None, 443}
        and model in {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-flash"}
    )
    default_window = 128000 if official_deepseek else 32768
    return {
        "context_window_tokens": int(
            profile.get("context_window_tokens", default_window)
        ),
        "response_tokens": int(profile.get("response_tokens", 4096)),
        "tool_result_tokens": int(profile.get("tool_result_tokens", 4096)),
        "context_chars": int(profile.get("context_chars", 96000)),
        "max_rounds": int(current_app.config.get("AI_RUNTIME_MAX_ROUNDS", 120)),
        "max_tool_calls": int(current_app.config.get("AI_RUNTIME_MAX_TOOL_CALLS", 120)),
        "max_active_seconds": int(
            current_app.config.get("AI_RUNTIME_MAX_ACTIVE_SECONDS", 1200)
        ),
        "read_concurrency": 4,
        "max_retries": 2,
    }

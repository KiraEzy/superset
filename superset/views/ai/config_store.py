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
"""Read/write helpers for the global AI connection configuration.

The config is persisted as a single encrypted JSON blob (see
``AiConnectionConfig``) mirroring the frontend ``StoredAiConnectionState`` shape.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from superset.constants import PASSWORD_MASK
from superset.extensions import db
from superset.models.ai_chat import AiConnectionConfig

logger = logging.getLogger(__name__)

# Singleton row id.
CONFIG_ID = 1

VALID_PROVIDERS = ("lmstudio", "openai", "gemini", "deepseek", "custom")
DEFAULT_PROVIDER = "gemini"

LLM_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "lmstudio": {"llmApiBaseUrl": "http://localhost:1234/v1", "llmModel": ""},
    "openai": {
        "llmApiBaseUrl": "https://api.openai.com/v1",
        "llmModel": "gpt-4o-mini",
    },
    "gemini": {
        "llmApiBaseUrl": "https://generativelanguage.googleapis.com/v1beta/openai",
        "llmModel": "gemini-2.5-flash",
    },
    "deepseek": {
        "llmApiBaseUrl": "https://api.deepseek.com/v1",
        "llmModel": "deepseek-chat",
    },
    "custom": {"llmApiBaseUrl": "", "llmModel": ""},
}

DEFAULT_MCP = {
    "mcpEnabled": True,
    "mcpServerUrl": "http://localhost:5008/mcp",
    "mcpBearerToken": "",
}

DEFAULT_AGENT = {
    "agentMaxIterations": 120,
    "systemPrompt": "",
}


def _default_state() -> dict[str, Any]:
    return {
        "llmProvider": DEFAULT_PROVIDER,
        "providerSettings": {},
        **DEFAULT_MCP,
        **DEFAULT_AGENT,
    }


def _normalize_state(parsed: dict[str, Any]) -> dict[str, Any]:
    state = _default_state()
    provider = parsed.get("llmProvider")
    if provider in VALID_PROVIDERS:
        state["llmProvider"] = provider
    provider_settings = parsed.get("providerSettings")
    if isinstance(provider_settings, dict):
        state["providerSettings"] = {
            key: value
            for key, value in provider_settings.items()
            if key in VALID_PROVIDERS and isinstance(value, dict)
        }
    if isinstance(parsed.get("mcpEnabled"), bool):
        state["mcpEnabled"] = parsed["mcpEnabled"]
    if isinstance(parsed.get("mcpServerUrl"), str):
        state["mcpServerUrl"] = parsed["mcpServerUrl"]
    if isinstance(parsed.get("mcpBearerToken"), str):
        state["mcpBearerToken"] = parsed["mcpBearerToken"]
    raw_iterations = parsed.get("agentMaxIterations")
    if isinstance(raw_iterations, int) and 1 <= raw_iterations <= 500:
        state["agentMaxIterations"] = raw_iterations
    if isinstance(parsed.get("systemPrompt"), str):
        state["systemPrompt"] = parsed["systemPrompt"]
    return state


def load_stored_state() -> dict[str, Any]:
    """Return the stored config blob (with real secrets), or defaults."""
    row = db.session.query(AiConnectionConfig).get(CONFIG_ID)
    if not row or not row.config:
        return _default_state()
    try:
        parsed = json.loads(row.config)
    except (ValueError, TypeError):
        logger.warning("Stored AI connection config is not valid JSON; using defaults")
        return _default_state()
    if not isinstance(parsed, dict):
        return _default_state()
    return _normalize_state(parsed)


def _provider_llm(state: dict[str, Any]) -> dict[str, str]:
    provider = state["llmProvider"]
    preset = LLM_PROVIDER_PRESETS.get(provider, LLM_PROVIDER_PRESETS[DEFAULT_PROVIDER])
    settings = state.get("providerSettings", {}).get(provider) or {}
    return {
        "llmApiBaseUrl": settings.get("llmApiBaseUrl") or preset["llmApiBaseUrl"],
        "llmModel": settings.get("llmModel") or preset["llmModel"],
        "llmApiKey": settings.get("llmApiKey", ""),
    }


def resolve_active_config() -> dict[str, Any]:
    """Flatten the stored state into the active connection config for chat."""
    state = load_stored_state()
    llm = _provider_llm(state)
    return {
        "llmProvider": state["llmProvider"],
        **llm,
        "mcpEnabled": state["mcpEnabled"],
        "mcpServerUrl": state["mcpServerUrl"],
        "mcpBearerToken": state["mcpBearerToken"],
        "agentMaxIterations": state["agentMaxIterations"],
        "systemPrompt": state["systemPrompt"],
    }


def masked_state() -> dict[str, Any]:
    """Return the stored state with secret fields masked for safe display."""
    state = load_stored_state()
    if state.get("mcpBearerToken"):
        state["mcpBearerToken"] = PASSWORD_MASK
    masked_provider_settings: dict[str, Any] = {}
    for provider, settings in state.get("providerSettings", {}).items():
        masked = dict(settings)
        if masked.get("llmApiKey"):
            masked["llmApiKey"] = PASSWORD_MASK
        masked_provider_settings[provider] = masked
    state["providerSettings"] = masked_provider_settings
    return state


def save_state(incoming: dict[str, Any]) -> dict[str, Any]:
    """Persist the incoming state, preserving masked secrets from the DB."""
    existing = load_stored_state()
    new_state = _normalize_state(incoming)

    # Preserve MCP bearer token if the client sent back the mask (unchanged).
    if incoming.get("mcpBearerToken") == PASSWORD_MASK:
        new_state["mcpBearerToken"] = existing.get("mcpBearerToken", "")

    # Preserve each provider's API key if the client sent back the mask.
    existing_providers = existing.get("providerSettings", {})
    for provider, settings in new_state.get("providerSettings", {}).items():
        if settings.get("llmApiKey") == PASSWORD_MASK:
            settings["llmApiKey"] = existing_providers.get(provider, {}).get(
                "llmApiKey", ""
            )

    row = db.session.query(AiConnectionConfig).get(CONFIG_ID)
    if not row:
        row = AiConnectionConfig(id=CONFIG_ID)
        db.session.add(row)
    row.config = json.dumps(new_state)
    db.session.commit()
    return new_state

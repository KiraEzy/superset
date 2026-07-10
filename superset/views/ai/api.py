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
from __future__ import annotations

import json
import logging
from typing import Any

from flask import current_app, request, stream_with_context
from flask_appbuilder.api import BaseApi, expose, protect, safe
from flask.wrappers import Response

from superset.views.ai import config_store
from superset.views.ai.proxy import (
    AiStreamError,
    chat_completion,
    iter_chat_completion_events,
    test_llm_connection,
    test_mcp_connection,
)

logger = logging.getLogger(__name__)


class AIRestApi(BaseApi):
    allow_browser_login = True
    resource_name = "ai"
    class_permission_name = "AI"
    openapi_spec_tag = "AI"
    # Reuse existing chat permission so streaming works without a new DB role grant.
    method_permission_name = {
        "test_llm": "chat",
        "test_mcp": "chat",
        "chat": "chat",
        "chat_stream": "chat",
    }

    def _json_response(self, status_code: int, payload: dict[str, Any]) -> Response:
        from flask import jsonify

        return jsonify(payload), status_code

    def _config_from_request(self) -> dict[str, Any]:
        return request.get_json(silent=True) or {}

    def _request_bearer_token(self) -> str | None:
        auth = request.headers.get("Authorization")
        if not auth:
            return None
        parts = auth.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        token = parts[1].strip()
        return token or None

    def _mcp_bearer_token_from_request(self, data: dict[str, Any]) -> str | None:
        if current_app.config.get("MCP_AUTH_ENABLED", False):
            from superset.views.ai.mcp_jwt import resolve_chat_mcp_bearer_token

            return resolve_chat_mcp_bearer_token()
        # Prefer the currently authenticated user's bearer token so MCP calls
        # execute with per-user identity instead of a shared dev fallback.
        request_token = self._request_bearer_token()
        if request_token:
            return request_token
        token = data.get("mcpBearerToken")
        if isinstance(token, str) and token.strip():
            return token.strip()
        return None

    def _resolve_mcp_bearer_token(self, stored_token: str | None) -> str | None:
        if current_app.config.get("MCP_AUTH_ENABLED", False):
            from superset.views.ai.mcp_jwt import resolve_chat_mcp_bearer_token

            return resolve_chat_mcp_bearer_token()
        # legacy: prefer request Authorization, else stored global token
        request_token = self._request_bearer_token()
        if request_token:
            return request_token
        if isinstance(stored_token, str) and stored_token.strip():
            return stored_token.strip()
        return None

    def _validate_mcp_auth_identity(
        self, *, mcp_enabled: bool, mcp_server_url: str, mcp_bearer_token: str | None
    ) -> None:
        if not (mcp_enabled and mcp_server_url):
            return
        if not current_app.config.get("MCP_AUTH_ENABLED", False):
            return
        if mcp_bearer_token:
            return
        raise ValueError(
            "MCP auth is enabled but no per-user bearer token was provided. "
            "Include an Authorization Bearer token in this request."
        )

    @expose("/test_llm/", methods=("POST",))
    @protect()
    @safe
    def test_llm(self) -> Response:
        data = self._config_from_request()
        try:
            result = test_llm_connection(
                llm_api_base_url=data.get("llmApiBaseUrl", ""),
                llm_api_key=data.get("llmApiKey"),
                llm_model=data.get("llmModel"),
            )
            return self._json_response(200, result)
        except Exception as ex:  # noqa: BLE001
            logger.exception("LLM connection test failed")
            return self._json_response(
                400,
                {"ok": False, "message": str(ex)},
            )

    @expose("/test_mcp/", methods=("POST",))
    @protect()
    @safe
    def test_mcp(self) -> Response:
        from superset.views.ai.mcp_jwt import McpJwtError

        data = self._config_from_request()
        try:
            mcp_bearer_token = self._mcp_bearer_token_from_request(data)
            result = test_mcp_connection(
                mcp_server_url=data.get("mcpServerUrl", ""),
                mcp_bearer_token=mcp_bearer_token,
            )
            return self._json_response(200, result)
        except McpJwtError as ex:
            return self._json_response(
                400,
                {"ok": False, "message": str(ex)},
            )
        except Exception as ex:  # noqa: BLE001
            logger.exception("MCP connection test failed")
            return self._json_response(
                400,
                {"ok": False, "message": str(ex)},
            )

    @expose("/chat/", methods=("POST",))
    @protect()
    @safe
    def chat(self) -> Response:
        from superset.views.ai.mcp_jwt import McpJwtError

        data = self._config_from_request()
        config = config_store.resolve_active_config()
        mcp_enabled = bool(config["mcpEnabled"])
        mcp_server_url = config["mcpServerUrl"]
        try:
            mcp_bearer_token = self._resolve_mcp_bearer_token(config["mcpBearerToken"])
            self._validate_mcp_auth_identity(
                mcp_enabled=mcp_enabled,
                mcp_server_url=mcp_server_url,
                mcp_bearer_token=mcp_bearer_token,
            )
            result = chat_completion(
                llm_api_base_url=config["llmApiBaseUrl"],
                llm_api_key=config["llmApiKey"],
                llm_model=config["llmModel"],
                messages=data.get("messages", []),
                mcp_enabled=mcp_enabled,
                mcp_server_url=mcp_server_url,
                mcp_bearer_token=mcp_bearer_token,
                agent_max_iterations=config["agentMaxIterations"],
                system_prompt=config["systemPrompt"],
            )
            return self._json_response(200, result)
        except McpJwtError as ex:
            return self._json_response(
                400,
                {"message": str(ex)},
            )
        except Exception as ex:  # noqa: BLE001
            logger.exception("AI chat failed")
            return self._json_response(
                400,
                {"message": str(ex)},
            )

    @expose("/chat/stream/", methods=("POST",))
    @protect()
    @safe
    def chat_stream(self) -> Response:
        from superset.views.ai.mcp_jwt import McpJwtError

        data = self._config_from_request()
        config = config_store.resolve_active_config()
        mcp_enabled = bool(config["mcpEnabled"])
        mcp_server_url = config["mcpServerUrl"]
        try:
            mcp_bearer_token = self._resolve_mcp_bearer_token(config["mcpBearerToken"])
        except McpJwtError as ex:
            return self._json_response(
                400,
                {"message": str(ex)},
            )
        self._validate_mcp_auth_identity(
            mcp_enabled=mcp_enabled,
            mcp_server_url=mcp_server_url,
            mcp_bearer_token=mcp_bearer_token,
        )

        def generate():
            try:
                for event in iter_chat_completion_events(
                    llm_api_base_url=config["llmApiBaseUrl"],
                    llm_api_key=config["llmApiKey"],
                    llm_model=config["llmModel"],
                    messages=data.get("messages", []),
                    mcp_enabled=mcp_enabled,
                    mcp_server_url=mcp_server_url,
                    mcp_bearer_token=mcp_bearer_token,
                    agent_max_iterations=config["agentMaxIterations"],
                    system_prompt=config["systemPrompt"],
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            except AiStreamError as ex:
                logger.exception("AI chat stream failed")
                yield f"data: {json.dumps(ex.to_event())}\n\n"
            except Exception as ex:  # noqa: BLE001
                logger.exception("AI chat stream failed")
                yield (
                    f"data: {json.dumps({'type': 'error', 'message': str(ex), 'source': 'agent'})}\n\n"
                )

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

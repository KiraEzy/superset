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
"""Authenticated catalogue, personal account and OAuth callback routes."""

from __future__ import annotations

from flask import jsonify, redirect, request
from flask.wrappers import Response
from flask_appbuilder.api import BaseApi, expose, protect, safe

from superset import security_manager
from superset.ai_runtime import connections
from superset.ai_runtime.api import runtime_errors


def _scope() -> tuple[int, int]:
    from superset.ai_runtime.store import current_scope

    return current_scope()


class AIConnectionCatalogueRestApi(BaseApi):
    """Separate administrator catalogue edits from owner-only account operations."""

    resource_name = "ai"
    class_permission_name = "AI"
    allow_browser_login = True
    openapi_spec_tag = "AI"
    method_permission_name = {
        "catalogue": "chat",
        "update_connection": "chat",
        "account": "chat",
        "oauth_start": "chat",
        "oauth_callback": "chat",
    }

    @staticmethod
    def _error(error: Exception) -> Response:
        return jsonify({"message": str(error)}), 400

    @staticmethod
    def _admin() -> bool:
        return security_manager.is_admin() and security_manager.can_access(
            "can_write", "AIConnectionConfig"
        )

    @expose("/connections/", methods=("GET", "POST"))
    @protect()
    @safe
    @runtime_errors
    def catalogue(self) -> Response:
        """List approved connections or explicitly register an admin-reviewed server."""
        try:
            if not self._admin():
                return jsonify(
                    {"message": "Connections are managed by your administrator"}
                ), 403
            user_id, post_id = _scope()
            if request.method == "POST":
                if not self._admin():
                    return jsonify(
                        {"message": "Administrator connection permission required"}
                    ), 403
                row = connections.save_connection(request.get_json(silent=True) or {})
                return jsonify({"result": {"id": row.id, "label": row.label}}), 201
            return jsonify({"result": connections.list_connections(user_id, post_id)})
        except connections.ConnectionError as ex:
            return self._error(ex)

    @expose("/connections/<connection_id>/", methods=("PUT",))
    @protect()
    @safe
    @runtime_errors
    def update_connection(self, connection_id: str) -> Response:
        """Edit reviewed destination configuration without exposing client secrets."""
        if not self._admin():
            return jsonify(
                {"message": "Administrator connection permission required"}
            ), 403
        try:
            row = connections.save_connection(
                request.get_json(silent=True) or {}, connection_id
            )
            return jsonify({"result": {"id": row.id, "label": row.label}})
        except connections.ConnectionError as ex:
            return self._error(ex)

    @expose("/connections/<connection_id>/account/", methods=("PUT", "DELETE"))
    @protect()
    @safe
    @runtime_errors
    def account(self, connection_id: str) -> Response:
        """Retire personal credentials without deleting existing encrypted records."""
        return jsonify(
            {
                "message": "Personal account linking is disabled. "
                "Use the global AI Connection settings."
            }
        ), 410

    @expose("/connections/<connection_id>/oauth/start/", methods=("POST",))
    @protect()
    @safe
    @runtime_errors
    def oauth_start(self, connection_id: str) -> Response:
        """Prevent stale clients from initiating personal OAuth linking."""
        return jsonify(
            {
                "message": "Personal OAuth linking is disabled. "
                "Use the global AI Connection settings."
            }
        ), 410

    @expose("/oauth/callback/", methods=("GET",))
    @protect()
    @safe
    @runtime_errors
    def oauth_callback(self) -> Response:
        """Return stale authorization redirects to the connection-free workspace."""
        return redirect("/ai/")

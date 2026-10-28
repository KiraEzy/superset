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

import logging
from typing import Any

from flask import request
from flask.wrappers import Response
from flask_appbuilder.api import BaseApi, expose, protect, safe

from superset import security_manager
from superset.extensions import event_logger
from superset.views.ai import config_store

logger = logging.getLogger(__name__)


class AIConnectionRestApi(BaseApi):
    """CRUD for the single, global AI connection configuration.

    Access is gated by a dedicated ``AIConnectionConfig`` permission so it can be
    granted to any role (not just Admin).
    """

    allow_browser_login = True
    resource_name = "ai_connection"
    class_permission_name = "AIConnectionConfig"
    openapi_spec_tag = "AI Connection"
    method_permission_name = {
        "get_config": "read",
        "save_config": "write",
        "access_options": "read",
        **{
            name: "write"
            for name in (
                "catalog",
                "verify_connection",
                "verify_model",
                "verification",
                "publish_models",
                "delete_connection",
                "reasoning_visibility",
                "model_settings",
            )
        },
    }

    def _json_response(self, status_code: int, payload: dict[str, Any]) -> Response:
        from flask import jsonify

        return jsonify(payload), status_code

    @expose("/", methods=("GET",))
    @protect()
    @safe
    @event_logger.log_this
    def get_config(self) -> Response:
        """Return the stored global config with secrets masked."""
        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        return self._json_response(200, {"result": config_store.masked_state()})

    @expose("/", methods=("PUT",))
    @protect()
    @safe
    @event_logger.log_this
    def save_config(self) -> Response:
        """Persist the global config, preserving masked secrets."""
        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        data = request.get_json(silent=True) or {}
        try:
            config_store.save_state(data)
        except Exception as ex:  # noqa: BLE001
            logger.exception("Failed to save AI connection config")
            return self._json_response(400, {"message": str(ex)})
        return self._json_response(200, {"result": config_store.masked_state()})

    @expose("/access-options/", methods=("GET",))
    @protect()
    @safe
    def access_options(self) -> Response:
        """Provide administrator-only principals and supported Focal tool names."""
        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        from pathlib import Path

        from flask_appbuilder.security.sqla.models import Role, User

        from superset.extensions import db
        from superset.utils import json

        catalog_path = Path(__file__).parents[2] / "ai_runtime" / "focal_catalog.json"
        tools = json.loads(catalog_path.read_text(encoding="utf-8")).get("tools", [])
        return self._json_response(
            200,
            {
                "result": {
                    "roles": [
                        name
                        for (name,) in db.session.query(Role.name)
                        .order_by(Role.name)
                        .all()
                    ],
                    "users": [
                        name
                        for (name,) in db.session.query(User.username)
                        .filter(User.active.is_(True))
                        .order_by(User.username)
                        .all()
                    ],
                    "tools": sorted(
                        {
                            tool["name"]
                            for tool in tools
                            if tool["name"] not in {"search_tools", "call_tool"}
                        }
                    ),
                }
            },
        )

    @expose("/models/", methods=("GET",))
    @protect()
    @safe
    def catalog(self) -> Response:
        """Administrator connection editor and discovered catalogue."""
        from superset.ai_runtime.model_catalog import catalogue

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        return self._json_response(200, {"result": catalogue(admin=True)})

    @expose("/models/<model_id>/settings", methods=("POST",))
    @protect()
    @safe
    def model_settings(self, model_id: str) -> Response:
        """Save administrator-owned budgets for subsequent Chat turns."""
        from superset.ai_runtime.model_settings import ModelSettingsConflictError, save

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        try:
            save(model_id, request.get_json(silent=True))
        except ModelSettingsConflictError as ex:
            return self._json_response(409, {"message": str(ex)})
        except ValueError as ex:
            return self._json_response(400, {"message": str(ex)})
        return self._json_response(200, {"result": {"saved": True}})

    @expose("/models/connections/verify", methods=("POST",))
    @protect()
    @safe
    def verify_connection(self) -> Response:
        """Queue verification without replacing working settings."""
        from superset.ai_runtime.model_catalog import queue_connection

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        try:
            identifier = queue_connection(request.get_json(silent=True) or {})
            return self._json_response(202, {"result": {"id": identifier}})
        except ValueError as ex:
            return self._json_response(400, {"message": str(ex)})

    @expose(
        "/models/connections/<connection_id>/reasoning-visibility", methods=("POST",)
    )
    @protect()
    @safe
    def reasoning_visibility(self, connection_id: str) -> Response:
        """Administrator opt-in for subsequent turns on a compatible connection."""
        from superset.ai_runtime.model_catalog import save_reasoning_visibility

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        try:
            data = request.get_json(silent=True) or {}
            save_reasoning_visibility(connection_id, data.get("showModelReasoning"))
            return self._json_response(200, {"result": True})
        except ValueError as ex:
            return self._json_response(400, {"message": str(ex)})

    @expose("/models/<model_id>/verify", methods=("POST",))
    @protect()
    @safe
    def verify_model(self, model_id: str) -> Response:
        """Verify one model before it can be published."""
        from superset.ai_runtime.model_catalog import queue_model

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        try:
            return self._json_response(202, {"result": {"id": queue_model(model_id)}})
        except ValueError as ex:
            return self._json_response(400, {"message": str(ex)})

    @expose("/models/jobs/<job_id>", methods=("GET",))
    @protect()
    @safe
    def verification(self, job_id: str) -> Response:
        """Expose progress without candidate credentials or provider bodies."""
        from superset.extensions import db
        from superset.models.ai_model_catalog import AiModelVerification

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        row = db.session.query(AiModelVerification).get(job_id)
        if not row:
            return self._json_response(404, {"message": "Verification not found"})
        return self._json_response(
            200,
            {
                "result": {
                    "id": row.id,
                    "status": row.status,
                    "message": row.message,
                    "connection_id": row.connection_id,
                }
            },
        )

    @expose("/models/publish", methods=("POST",))
    @protect()
    @safe
    def publish_models(self) -> Response:
        """Atomically publish the ordered selection and default."""
        from superset.ai_runtime.model_catalog import catalogue, publish

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        try:
            data = request.get_json(silent=True) or {}
            identifiers, default = data.get("ids"), data.get("default")
            if not isinstance(identifiers, list) or not isinstance(default, str):
                raise ValueError("Choose available models and a default model")
            publish(identifiers, default)
            return self._json_response(200, {"result": catalogue(admin=True)})
        except (ValueError, TypeError) as ex:
            return self._json_response(400, {"message": str(ex)})

    @expose("/models/connections/<connection_id>", methods=("DELETE",))
    @protect()
    @safe
    def delete_connection(self, connection_id: str) -> Response:
        """Remove availability without deleting historical turn snapshots."""
        from superset.extensions import db
        from superset.models.ai_model_catalog import AiModel, AiModelConnection

        if not security_manager.is_admin():
            return self._json_response(
                403, {"message": "Administrator access required"}
            )
        models = db.session.query(AiModel).filter_by(connection_id=connection_id).all()
        if any(m.is_default for m in models):
            return self._json_response(
                409,
                {"message": "Publish another default before deleting this connection"},
            )
        db.session.query(AiModel).filter_by(connection_id=connection_id).delete()
        db.session.query(AiModelConnection).filter_by(id=connection_id).delete()
        db.session.commit()
        return self._json_response(200, {"result": True})

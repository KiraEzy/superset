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
from flask_appbuilder.api import BaseApi, expose, protect, safe
from flask.wrappers import Response

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
        return self._json_response(200, {"result": config_store.masked_state()})

    @expose("/", methods=("PUT",))
    @protect()
    @safe
    @event_logger.log_this
    def save_config(self) -> Response:
        """Persist the global config, preserving masked secrets."""
        data = request.get_json(silent=True) or {}
        try:
            config_store.save_state(data)
        except Exception as ex:  # noqa: BLE001
            logger.exception("Failed to save AI connection config")
            return self._json_response(400, {"message": str(ex)})
        return self._json_response(200, {"result": config_store.masked_state()})

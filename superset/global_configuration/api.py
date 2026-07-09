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
from flask_login import login_required
from flask.wrappers import Response

from superset.extensions import db, event_logger
from superset.global_configuration import store

logger = logging.getLogger(__name__)


class GlobalConfigurationRestApi(BaseApi):
    allow_browser_login = True
    resource_name = "global_configuration"
    class_permission_name = "GlobalConfiguration"
    openapi_spec_tag = "Global Configuration"
    method_permission_name = {
        "get_config": "read",
        "save_config": "write",
        "delete_config": "write",
        # get_public intentionally not listed — uses login_required only
    }
    include_route_methods = {
        "get_public",
        "get_config",
        "save_config",
        "delete_config",
    }

    def _json(self, status: int, payload: dict[str, Any]) -> Response:
        from flask import jsonify

        return jsonify(payload), status

    @expose("/public/", methods=("GET",))
    @login_required
    @safe
    @event_logger.log_this
    def get_public(self) -> Response:
        """Public keys for any authenticated user (no GlobalConfiguration perm)."""
        return self._json(200, {"result": store.public_map()})

    @expose("/", methods=("GET",))
    @protect()
    @safe
    @event_logger.log_this
    def get_config(self) -> Response:
        rows = [
            {"key": r.key, "value": r.value}
            for r in store.get_all_rows()
        ]
        return self._json(
            200,
            {"result": {"known": store.effective_known_map(), "rows": rows}},
        )

    @expose("/", methods=("PUT",))
    @protect()
    @safe
    @event_logger.log_this
    def save_config(self) -> Response:
        data = request.get_json(silent=True) or {}
        # Accept either flat known map or { known: {...}, entries: {...} }
        entries: dict[str, Any] = {}
        if "known" in data or "entries" in data:
            entries.update(data.get("known") or {})
            entries.update(data.get("entries") or {})
        else:
            entries.update(data)
        try:
            known = store.upsert_entries(entries)
        except ValueError as ex:
            db.session.rollback()
            return self._json(400, {"message": str(ex)})
        except Exception as ex:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Failed to save global configuration")
            return self._json(400, {"message": str(ex)})
        rows = [
            {"key": r.key, "value": r.value}
            for r in store.get_all_rows()
        ]
        return self._json(200, {"result": {"known": known, "rows": rows}})

    @expose("/<string:key>", methods=("DELETE",))
    @protect()
    @safe
    @event_logger.log_this
    def delete_config(self, key: str) -> Response:
        try:
            store.delete_key(key)
        except Exception as ex:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Failed to delete global configuration key")
            return self._json(400, {"message": str(ex)})
        return self._json(
            200,
            {
                "result": {
                    "known": store.effective_known_map(),
                    "rows": [
                        {"key": r.key, "value": r.value}
                        for r in store.get_all_rows()
                    ],
                }
            },
        )

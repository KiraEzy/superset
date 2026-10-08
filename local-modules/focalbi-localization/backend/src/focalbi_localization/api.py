# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
"""Namespaced extension API, enforcing native access on every resource."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from flask import request, Response
from flask_appbuilder.api import expose, permission_name, protect, safe
from superset.extensions import security_manager
from superset_core.rest_api.api import RestApi
from superset_core.rest_api.decorators import api

from .catalog import ConflictError, LOCALES, resolved, Store, validate_entries
from .resources import actor, fields, load, SUPPORTED

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def store() -> Store:
    """Connect only to the module's configured database; never native metadata."""
    return Store(os.environ["FOCALBI_LOCALIZATION_DATABASE_URI"])


@api(id="catalog", name="Content localization", resource_name="catalog")
class LocalizationApi(RestApi):
    """Guest-safe bundle reads and authenticated resource authoring."""

    class_permission_name = "FocalLocalization"
    csrf_exempt = False

    @expose("/resolve/<kind>/<int:native_id>", methods=("GET",))
    @protect()
    @permission_name("read")
    @safe
    def resolve_identity(self, kind: str, native_id: int) -> Response:
        """Resolve existing native bindings without replacing definition loaders."""

        def action() -> Response:
            from superset.connectors.sqla.models import SqlaTable
            from superset.extensions import db
            from superset.models.dashboard import Dashboard
            from superset.models.slice import Slice

            model = {"dashboard": Dashboard, "chart": Slice, "dataset": SqlaTable}.get(
                kind
            )
            if model is None:
                raise ValueError("Unsupported resource type")
            resource = (
                db.session.query(model).filter(model.id == native_id).one_or_none()
            )
            if resource is None:
                raise LookupError("Resource not found")
            load(kind, str(resource.uuid))
            editable = False
            if not security_manager.is_guest_user():
                try:
                    load(kind, str(resource.uuid), write=True)
                    editable = True
                except PermissionError:
                    pass
            return self.response(
                200, result={"uuid": str(resource.uuid), "editable": editable}
            )

        return self.dispatch(action)

    def dispatch(self, action: Any) -> Response:
        """Map domain errors without exposing SQL or secrets."""
        try:
            return action()
        except ConflictError as error:
            return self.response(409, message=str(error))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            return self.response(400, message=str(error))
        except PermissionError as error:
            return self.response(403, message=str(error))
        except LookupError:
            return self.response(404, message="Resource not found")
        except Exception:
            logger.exception("Localization catalog unavailable")
            return self.response(
                503,
                message="Translation catalog unavailable; original text remains usable",
            )

    @expose("/resource/<kind>/<uid>", methods=("GET", "PUT"))
    @protect()
    @permission_name("read")
    @safe
    def resource(self, kind: str, uid: str) -> Response:
        """Discover/read/save one resource; guests cannot browse author catalogs."""

        def action() -> Response:
            if security_manager.is_guest_user():
                raise PermissionError("Translation authoring is unavailable to guests")
            resource = load(kind, uid, write=request.method == "PUT")
            descriptors = fields(kind, resource)
            if request.method == "PUT":
                data = request.get_json()
                if not isinstance(data, dict):
                    raise ValueError("Catalog save must be an object")
                entries = validate_entries(data["entries"], descriptors)
                revision = store().save_many(
                    [
                        {
                            "type": kind,
                            "uuid": uid,
                            "revision": data["revision"],
                            "entries": entries,
                        }
                    ],
                    actor(),
                )[0]
                return self.response(200, result={"revision": revision})
            data = store().read(kind, uid)
            return self.response(
                200,
                result={
                    "version": 1,
                    "type": kind,
                    "uuid": str(resource.uuid),
                    "fields": descriptors,
                    "supportedVizTypes": sorted(SUPPORTED),
                    "unsupportedVisualizations": [
                        {"title": chart.slice_name, "type": chart.viz_type}
                        for chart in (
                            resource.slices
                            if kind == "dashboard"
                            else [resource]
                            if kind == "chart"
                            else []
                        )
                        if chart.viz_type not in SUPPORTED
                    ],
                    **data,
                },
            )

        return self.dispatch(action)

    @expose("/export/<kind>/<uid>", methods=("GET",))
    @protect()
    @permission_name("read")
    @safe
    def export_bundle(self, kind: str, uid: str) -> Response:
        """Export one authorized author catalog in the validated import format."""

        def action() -> Response:
            if security_manager.is_guest_user():
                raise PermissionError("Guests cannot export author catalogs")
            resource = load(kind, uid)
            data = store().read(kind, str(resource.uuid))
            return self.response(
                200,
                result={
                    "version": 1,
                    "resources": [{"type": kind, "uuid": str(resource.uuid), **data}],
                    "remap": {},
                    "fieldRemap": {},
                },
            )

        return self.dispatch(action)

    @expose("/bundle/<kind>/<uid>", methods=("GET",))
    @protect()
    @permission_name("read")
    @safe
    def bundle(self, kind: str, uid: str) -> Response:
        """Load a presentation bundle restricted to the authorized native resource."""

        def action() -> Response:
            locale = request.args.get("locale", "en")
            if locale not in LOCALES:
                raise ValueError("Unsupported locale")
            resource = load(kind, uid)
            resources: dict[str, Any] = {}

            def append(resource_kind: str, item: Any) -> dict[str, Any]:
                key = resource_kind + "/" + str(item.uuid)
                if key in resources:
                    return resources[key]
                descriptors = fields(resource_kind, item)
                data = store().read(resource_kind, str(item.uuid))
                entry = {
                    "uuid": str(item.uuid),
                    "fields": descriptors,
                    "translations": resolved(data["entries"], descriptors, locale),
                    "revision": data["revision"],
                }
                resources[key] = entry
                return entry

            append(kind, resource)
            charts = (
                resource.slices
                if kind == "dashboard"
                else [resource]
                if kind == "chart"
                else []
            )
            bindings = {}
            datasets = {}
            for chart in charts:
                if (
                    not security_manager.is_guest_user()
                    and not security_manager.can_access_chart(chart)
                ):
                    continue
                append("chart", chart)
                dataset = chart.datasource
                if dataset is not None:
                    append("dataset", dataset)
                    datasets[str(dataset.id)] = str(dataset.uuid)
                bindings[str(chart.id)] = {
                    "uuid": str(chart.uuid),
                    "datasetUuid": str(dataset.uuid) if dataset else None,
                }
            domains = []
            if kind == "dashboard":
                for embedded in resource.embedded:
                    domains.extend(embedded.allowed_domains or [])
            return self.response(
                200,
                result={
                    "version": 1,
                    "locale": locale,
                    "kind": kind,
                    "uuid": str(resource.uuid),
                    "resources": resources,
                    "charts": bindings,
                    "datasets": datasets,
                    "allowedOrigins": domains,
                },
            )

        return self.dispatch(action)

    @expose("/import", methods=("POST",))
    @protect()
    @permission_name("read")
    @safe
    def import_bundle(self) -> Response:
        """Validate and authorize the entire batch before a transactional import."""

        def action() -> Response:
            if security_manager.is_guest_user():
                raise PermissionError("Guests cannot import translations")
            data = request.get_json()
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("remap", {}), dict)
                or not isinstance(data.get("fieldRemap", {}), dict)
            ):
                raise ValueError("Import and remapping must be objects")
            if (
                data.get("version") != 1
                or not isinstance(data.get("resources"), list)
                or len(data["resources"]) > 100
            ):
                raise ValueError("Unsupported translation bundle")
            output = []
            seen = set()
            for item in data["resources"]:
                if not isinstance(item, dict) or not isinstance(
                    item.get("entries"), dict
                ):
                    raise ValueError(
                        "Each imported resource must contain an entries object"
                    )
                uid = data.get("remap", {}).get(item["uuid"], item["uuid"])
                resource = load(item["type"], uid, write=True)
                key = item["type"] + "/" + uid
                if key in seen:
                    raise ValueError("Duplicate target resource")
                seen.add(key)
                mapping = data.get("fieldRemap", {}).get(key, {})
                if not isinstance(mapping, dict):
                    raise ValueError("Field mapping must be an object")
                entries = {
                    mapping.get(name, name): value
                    for name, value in item["entries"].items()
                }
                if len(entries) != len(item["entries"]):
                    raise ValueError("Field mapping contains duplicate targets")
                output.append(
                    {
                        "type": item["type"],
                        "uuid": uid,
                        "revision": item["revision"],
                        "entries": validate_entries(
                            entries, fields(item["type"], resource)
                        ),
                    }
                )
            return self.response(
                200, result={"revisions": store().save_many(output, actor())}
            )

        return self.dispatch(action)

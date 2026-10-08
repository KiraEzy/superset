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
"""Provision owned persistence and resource-gated extension read permissions."""

import json
import os
import sys

sys.path.insert(0, "/app/focalbi-localization/extension/dist/backend/src")
from focalbi_localization.catalog import Store  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine.url import make_url  # noqa: E402
from superset.app import create_app  # noqa: E402
from superset.extensions import db, security_manager  # noqa: E402

app = create_app()
with app.app_context():
    uri = make_url(os.environ["FOCALBI_LOCALIZATION_DATABASE_URI"])
    if uri.database != "focalbi_localization" or uri.username != "focalbi_localization":
        raise RuntimeError("Refusing a database or role outside module ownership")
    admin_engine = create_engine(
        app.config["SQLALCHEMY_DATABASE_URI"], isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname=:name"), {"name": uri.username}
        ).scalar()
        if not exists:
            connection.execute(
                text("CREATE ROLE focalbi_localization LOGIN PASSWORD :password"),
                {"password": uri.password},
            )
        owner = connection.execute(
            text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database "
                "WHERE datname='focalbi_localization'"
            )
        ).scalar()
        if owner and owner != uri.username:
            raise RuntimeError("Existing database belongs to another owner")
        if not owner:
            connection.execute(
                text("CREATE DATABASE focalbi_localization OWNER focalbi_localization")
            )
    Store(uri.render_as_string(hide_password=False)).migrate()
    recorded = []
    permissions = [
        (
            "can_read",
            "FocalLocalization",
            ("Admin", "Alpha", "Gamma", "EmbeddedViewer"),
        ),
        # Only static packaged frontend chunks, not catalog listing or writes.
        ("can_content", "ExtensionsRestApi", ("Admin", "Alpha", "Gamma")),
        ("can_get_list", "ExtensionsRestApi", ("Admin", "Alpha", "Gamma")),
    ]
    for action, view, names in permissions:
        permission = security_manager.add_permission_view_menu(action, view)
        for name in names:
            role = security_manager.find_role(name)
            if role and permission not in role.permissions:
                security_manager.add_permission_role(role, permission)
                recorded.append({"role": name, "permission": action, "view": view})
            elif role and view == "FocalLocalization":
                # This namespaced permission is exclusively owned by this module.
                recorded.append({"role": name, "permission": action, "view": view})
    db.session.commit()
    print(
        "FOCALBI_LOCALIZATION_SETUP="
        + json.dumps(
            {"database": "focalbi_localization", "schemaVersion": 1, "grants": recorded}
        )
    )

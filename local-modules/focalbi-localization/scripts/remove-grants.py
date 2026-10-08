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
"""Remove only permission grants recorded during module activation."""

import json
import sys

from superset.app import create_app
from superset.extensions import db, security_manager

app = create_app()
with app.app_context():
    grants = json.loads(sys.stdin.read().lstrip("\ufeff"))
    permitted = {
        ("can_read", "FocalLocalization"),
        ("can_content", "ExtensionsRestApi"),
        ("can_get_list", "ExtensionsRestApi"),
    }
    for item in grants:
        if (item["permission"], item["view"]) not in permitted or item["role"] not in {
            "Admin",
            "Alpha",
            "Gamma",
            "EmbeddedViewer",
        }:
            raise RuntimeError("Permission receipt contains an unowned grant")
        role = security_manager.find_role(item["role"])
        permission = security_manager.find_permission_view_menu(
            item["permission"], item["view"]
        )
        if role and permission and permission in role.permissions:
            security_manager.del_permission_role(role, permission)
    db.session.commit()
    print("Removed only recorded localization permission grants")

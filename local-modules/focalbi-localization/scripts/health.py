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
"""Check the independent catalog database without reading resource content."""

import json
import os
import sys

from sqlalchemy import select
from superset.app import create_app

sys.path.insert(0, "/app/focalbi-localization/extension/dist/backend/src")
from focalbi_localization.catalog import migrations, Store  # noqa: E402

store = Store(os.environ["FOCALBI_LOCALIZATION_DATABASE_URI"])
with store.engine.connect() as connection:
    version = connection.execute(select(migrations.c.version)).scalar()
    if version != 1:
        raise RuntimeError("Catalog migration compatibility failed")
app = create_app()
if not any(
    str(rule).startswith("/extensions/focalbi/content-localization/catalog/resolve/")
    for rule in app.url_map.iter_rules()
):
    raise RuntimeError("Localization extension registration failed")
print(
    json.dumps(
        {"database": "healthy", "schemaVersion": version, "extension": "registered"}
    )
)

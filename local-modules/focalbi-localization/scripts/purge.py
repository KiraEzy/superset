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
"""Explicitly purge only the fixed module-owned database after ownership checks."""

from sqlalchemy import create_engine, text
from superset.app import create_app

app = create_app()
with app.app_context():
    engine = create_engine(
        app.config["SQLALCHEMY_DATABASE_URI"], isolation_level="AUTOCOMMIT"
    )
    with engine.connect() as connection:
        owner = connection.execute(
            text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database "
                "WHERE datname='focalbi_localization'"
            )
        ).scalar()
        if owner != "focalbi_localization":
            raise RuntimeError("Module database ownership check failed")
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname='focalbi_localization' AND pid<>pg_backend_pid()"
            )
        )
        connection.execute(text("DROP DATABASE focalbi_localization"))
        connection.execute(text("DROP ROLE focalbi_localization"))
    print("Purged only focalbi_localization database and role")

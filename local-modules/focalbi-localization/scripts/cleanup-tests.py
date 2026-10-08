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
"""Remove only UUID-verified synthetic resources recorded by localization QA."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def validate(ledger: dict[str, Any]) -> None:
    """Reject foreign receipts before any mutation."""
    if ledger.get("owner") != "focalbi.localization.tests":
        raise ValueError("Unowned fixture receipt")
    for item in ledger["resources"]:
        if item["type"] not in {"dashboard", "chart", "dataset"}:
            raise ValueError("Unsupported resource type in fixture receipt")


def main() -> None:
    """Clean native fixtures first, then their owned catalog rows."""
    if "--catalogs" in sys.argv:
        sys.path.insert(0, "/app/focalbi-localization/extension/dist/backend/src")
        from focalbi_localization.catalog import catalogs, identity, Store

        ledger = json.loads(sys.stdin.read())
        validate(ledger)
        store = Store(os.environ["FOCALBI_LOCALIZATION_DATABASE_URI"])
        with store.engine.begin() as connection:
            for item in ledger["resources"]:
                kind, uid = identity(item["type"], item["uuid"])
                connection.execute(
                    catalogs.delete().where(
                        catalogs.c.resource_type == kind,
                        catalogs.c.resource_uuid == uid,
                    )
                )
        print("Removed recorded synthetic translation catalogs")
        return
    from http_client import Client

    path = ROOT / ".runtime/localization-test-resources.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    validate(ledger)
    client = Client("http://localhost:8088", ROOT / ".runtime/admin-cookie.json")
    present = []
    # Validate every resource before deleting any, and allow interrupted cleanup.
    for item in ledger["resources"]:
        try:
            native = client.request(f"/api/v1/{item['type']}/{item['id']}")["result"]
        except RuntimeError as error:
            if str(error).startswith("HTTP 404:"):
                continue
            raise
        if native["uuid"] != item["uuid"]:
            raise ValueError("Native UUID does not match the owned fixture receipt")
        present.append(item)
    order = {"dashboard": 0, "chart": 1, "dataset": 2}
    for item in sorted(present, key=lambda item: order[item["type"]]):
        client.request(f"/api/v1/{item['type']}/{item['id']}", method="DELETE")
    docker_path = shutil.which("docker")
    if not docker_path:
        raise RuntimeError("Docker is required for owned catalog cleanup")
    subprocess.run(  # noqa: S603 — resolved Docker command and module-owned script
        [
            docker_path,
            "exec",
            "-i",
            "superset_app",
            "python",
            "/app/focalbi-localization/scripts/cleanup-tests.py",
            "--catalogs",
        ],
        input=json.dumps(ledger),
        text=True,
        check=True,
    )
    path.unlink()
    print(f"Removed {len(present)} UUID-verified native test resources")


if __name__ == "__main__":
    main()

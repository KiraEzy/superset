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
"""Materialize an authorized saved snapshot; preserve target dataset identities."""
# SQL is trusted native author configuration; identifiers use identity(), not input SQL.
# ruff: noqa: S608

import argparse
import hashlib
import json  # noqa: TID251 -- Standalone operator, outside the Superset runtime.
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "local-modules/focalbi-localization/scripts"))
from http_client import Client  # noqa: E402


def identity(value: str) -> str:
    """Quote an operator-selected PostgreSQL identifier without accepting SQL."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ValueError("Invalid PostgreSQL identifier")
    return f'"{value}"'


def run_sql(config: dict, sql: str) -> str:
    """Send SQL on stdin to the explicitly configured analytical database."""
    result = subprocess.run(  # noqa: S603 -- Operator configuration, argv only; no shell.
        [  # noqa: S607 -- Use the installed Docker CLI on the operator's PATH.
            "docker",
            "exec",
            "-i",
            config["postgres_container"],
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            config["role"],
            "-d",
            config["database"],
        ],
        input=sql,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[:1500])
    return result.stdout.strip()


def stable_fields(dataset: dict) -> dict:
    """Compare native authoring metadata; only the SQL source should change."""
    keys = (
        "uuid",
        "columns",
        "metrics",
        "owners",
        "extra",
        "template_params",
        "cache_timeout",
        "main_dttm_col",
        "always_filter_main_dttm",
        "is_managed_externally",
        "description",
        "table_name",
    )
    return {key: dataset.get(key) for key in keys}


def main() -> None:  # noqa: C901 -- Ordered migration and rollback guard checks.
    """Prepare, apply, or reverse a verified snapshot replacement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://localhost:8088")
    parser.add_argument("--cookie", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "materialize.json")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", action="store_true")
    action.add_argument("--reapply", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    table = f"{identity(config['schema'])}.{identity(config['table'])}"
    client = Client(args.origin, args.cookie)
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    receipt_path = runtime / "materialization.json"

    def read(resource: dict) -> dict:
        result = client.request(f"/api/v1/dataset/{resource['id']}")["result"]
        if result["uuid"] != resource["uuid"]:
            raise RuntimeError("Dataset identity changed")
        return result

    def update(resource: dict, sql: str, before: dict) -> None:
        payload = {
            "sql": sql,
            "always_filter_main_dttm": before.get("always_filter_main_dttm", False),
            "is_managed_externally": before.get("is_managed_externally", False),
        }
        client.request(f"/api/v1/dataset/{resource['id']}", payload, "PUT")
        after = read(resource)
        if after["sql"] != sql or stable_fields(after) != stable_fields(before):
            raise RuntimeError(
                "Native metadata verification failed; inspect backup before continuing"
            )

    if args.rollback or args.reapply:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
        if receipt["table"] != table:
            raise RuntimeError("Configured table does not match the receipt")
        if args.reapply:
            marker = run_sql(config, f"SELECT obj_description('{table}'::regclass);")
            if marker != "focalbi.snapshot." + receipt["source_sha256"]:
                raise RuntimeError("Physical snapshot ownership does not match")
            source_sql = read(receipt["source"])["sql"].strip().rstrip(";")
            if (
                hashlib.sha256(source_sql.encode()).hexdigest()
                != receipt["source_sha256"]
            ):
                raise RuntimeError("Original snapshot changed since materialization")
            difference = run_sql(
                config,
                f"SELECT count(*) FROM ((SELECT * FROM {table} "
                f"EXCEPT ALL ({source_sql})) UNION ALL (({source_sql}) "
                f"EXCEPT ALL SELECT * FROM {table})) differences;",
            )
            if difference != "0":
                raise RuntimeError("Physical snapshot no longer matches the original")
            run_sql(
                config,
                f"SET ROLE {identity(config['reader_role'])}; "
                f"SELECT 1 FROM {table} LIMIT 1;",
            )
        previous = []
        for item in receipt["targets"]:
            current = read(item)
            if current["sql"] not in (item["after"], item["before"]):
                raise RuntimeError(
                    "Dataset changed since migration; refusing to overwrite"
                )
            previous.append((item, current))
        attempted = []
        try:
            for item, current in previous:
                attempted.append((item, current))
                update(item, item["before" if args.rollback else "after"], current)
        except Exception:
            for item, current in reversed(attempted):
                latest = read(item)
                if latest["sql"] in (item["before"], item["after"]):
                    update(item, current["sql"], latest)
            raise
        receipt["active"] = bool(args.reapply)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(
            "Materialized SQL restored."
            if args.reapply
            else "Original SQL restored. Physical snapshot retained."
        )
        return

    source = read(config["source"])
    source_sql = source["sql"].strip().rstrip(";")
    targets = []
    for resource in config["targets"]:
        dataset = read(resource)
        if dataset["database"]["id"] != source["database"]["id"]:
            raise RuntimeError("Source and target databases differ")
        if dataset["sql"].count(source_sql) != 1:
            raise RuntimeError("Target must contain the exact source SQL once")
        targets.append(
            {
                **resource,
                "before": dataset["sql"],
                "after": dataset["sql"].replace(source_sql, f"SELECT * FROM {table}"),
                "metadata": dataset,
            }
        )
    if receipt_path.exists():
        raise RuntimeError(
            "Existing receipt: review it rather than replacing rollback history"
        )
    receipt = {
        "active": False,
        "table": table,
        "source": config["source"],
        "source_sha256": hashlib.sha256(source_sql.encode()).hexdigest(),
        "targets": targets,
    }
    (runtime / "prepared.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "prepared": [
                    {
                        "id": t["id"],
                        "before_chars": len(t["before"]),
                        "after_chars": len(t["after"]),
                    }
                    for t in targets
                ]
            }
        )
    )
    if not args.apply:
        return

    # CREATE without IF NOT EXISTS refuses any pre-existing operator-owned table.
    marker = "focalbi.snapshot." + receipt["source_sha256"]
    run_sql(
        config,
        f"BEGIN; CREATE TABLE {table} AS {source_sql}; "
        f"COMMENT ON TABLE {table} IS '{marker}'; "
        f"GRANT SELECT ON TABLE {table} TO {identity(config['reader_role'])}; "
        f"ANALYZE {table}; COMMIT;",
    )
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    mismatch = run_sql(
        config,
        f"SELECT count(*) FROM ((SELECT * FROM {table} EXCEPT ALL ({source_sql})) "
        f"UNION ALL (({source_sql}) EXCEPT ALL SELECT * FROM {table})) differences;",
    )
    if mismatch != "0":
        raise RuntimeError("Snapshot row multiset differs; datasets were not changed")
    # Verify the actual analytical connection can read before changing dataset SQL.
    run_sql(
        config,
        f"SET ROLE {identity(config['reader_role'])}; SELECT 1 FROM {table} LIMIT 1;",
    )
    receipt["rows"] = int(run_sql(config, f"SELECT count(*) FROM {table};"))
    attempted = []
    try:
        for item in targets:
            # Recheck immediately before writing to avoid overwriting another edit.
            current = read(item)
            if current["sql"] != item["before"] or stable_fields(
                current
            ) != stable_fields(item["metadata"]):
                raise RuntimeError("Dataset edited after preparation")
            attempted.append(item)
            update(item, item["after"], current)
    except Exception:
        for item in reversed(attempted):
            current = read(item)
            if current["sql"] == item["after"]:
                update(item, item["before"], current)
        raise
    receipt["active"] = True
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "active": True,
                "rows": receipt["rows"],
                "equal_row_multiset": True,
                "dataset_ids": [item["id"] for item in targets],
            }
        )
    )


if __name__ == "__main__":
    main()

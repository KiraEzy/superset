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
"""Record and remove only the module-owned documentation blocks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = [
    ("<!-- focalbi.rendering:begin -->", "<!-- focalbi.rendering:end -->"),
    ("{/* focalbi.rendering:begin */}", "{/* focalbi.rendering:end */}"),
]


def block(content: str) -> str:
    """Require one unambiguous ownership marker pair."""
    begin, end = next((pair for pair in MARKERS if pair[0] in content), MARKERS[0])
    if content.count(begin) != 1 or content.count(end) != 1:
        raise ValueError("Documentation ownership markers are missing or ambiguous")
    start = content.index(begin)
    stop = content.index(end) + len(end)
    if stop < start:
        raise ValueError("Documentation marker order is invalid")
    return content[start:stop]


def owned_path(repository: Path, relative: str) -> Path:
    """Resolve a recorded documentation path only within its repository."""
    result = (repository / relative).resolve()
    if not result.is_relative_to(repository.resolve()):
        raise ValueError("Documentation path escapes the repository")
    return result


def remove_blocks(repository: Path, records: list[dict]) -> None:
    """Validate all recorded content before touching any document."""
    updates = []
    for record in records:
        path = owned_path(repository, record["path"])
        content = path.read_text(encoding="utf-8")
        section = block(content)
        if hashlib.sha256(section.encode()).hexdigest() != record["sha256"]:
            raise ValueError(
                "Module documentation changed after activation; removal stopped"
            )
        updates.append((path, content.replace(section, "", 1)))
    for path, content in updates:
        path.write_text(content, encoding="utf-8")


def main() -> None:
    """Record ownership hashes or remove verified module documentation blocks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["record", "remove"])
    args = parser.parse_args()
    repository = ROOT.parents[1]
    path = ROOT / ".runtime/resources.json"
    ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    if ledger.get("owner") != "focalbi.rendering":
        raise ValueError("Unknown resource ledger")
    if args.operation == "record":
        documents = json.loads((ROOT / "deployment/documentation.json").read_text())
        ledger["documentation"] = [
            {
                "path": relative,
                "sha256": hashlib.sha256(
                    block(
                        owned_path(repository, relative).read_text(encoding="utf-8")
                    ).encode()
                ).hexdigest(),
            }
            for relative in documents
        ]
    else:
        remove_blocks(repository, ledger.get("documentation", []))
        ledger["documentation"] = []
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

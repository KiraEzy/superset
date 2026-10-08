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
"""Freeze renderer sources and runtime dependencies without touching upstream."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
FRONTEND = REPO / "superset-frontend"


def digest(path: Path) -> str:
    """Hash file bytes for immutable source provenance."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot() -> None:
    """Copy the pinned source revision and record file identities and hashes."""
    git_binary = shutil.which("git")
    if not git_binary:
        raise RuntimeError("Git is required to record the snapshot revision")
    manifest_path = ROOT / "provenance.json"
    if manifest_path.exists():
        raise SystemExit(
            "Snapshot exists; updates require an explicit reviewed migration."
        )
    records: dict[str, dict[str, str]] = {}
    sources = {
        "baseline/echarts": "plugins/plugin-chart-echarts/src",
        "baseline/table": "plugins/plugin-chart-table/src",
    }
    for target, source in sources.items():
        source_path = FRONTEND / source
        for path in source_path.rglob("*"):
            if (
                not path.is_file()
                or any(
                    part in {"test", "tests", "stories", "__snapshots__"}
                    for part in path.relative_to(source_path).parts
                )
                or any(mark in path.name for mark in (".test.", ".stories.", ".story."))
            ):
                continue
            destination = ROOT / "vendor" / target / path.relative_to(source_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            records[destination.relative_to(ROOT).as_posix()] = {
                "source": path.relative_to(REPO).as_posix(),
                "sha256": digest(path),
            }
    shutil.copytree(ROOT / "vendor/baseline", ROOT / "vendor/fork")
    shutil.copy2(FRONTEND / "package-lock.json", ROOT / "upstream-package-lock.json")
    shutil.copy2(REPO / "LICENSE.txt", ROOT / "LICENSE.txt")
    shutil.copy2(REPO / "NOTICE", ROOT / "NOTICE")
    manifest_path.write_text(
        json.dumps(
            {
                "revision": subprocess.check_output(  # noqa: S603 - fixed read-only git invocation
                    [
                        git_binary,
                        "rev-parse",
                        "HEAD",
                    ],
                    cwd=REPO,
                    text=True,
                ).strip(),
                "files": records,
                "dependencyLockSha256": digest(ROOT / "upstream-package-lock.json"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Frozen {len(records)} files and created independent fork renderers")


def verify() -> None:
    """Reject a baseline or shared snapshot whose bytes differ from provenance."""
    provenance = json.loads((ROOT / "provenance.json").read_text(encoding="utf-8"))
    changed = [
        name
        for name, item in provenance["files"].items()
        if not (ROOT / name).is_file() or digest(ROOT / name) != item["sha256"]
    ]
    if (
        digest(ROOT / "upstream-package-lock.json")
        != provenance["dependencyLockSha256"]
    ):
        changed.append("upstream-package-lock.json")
    if changed:
        raise SystemExit("Immutable snapshot changed: " + ", ".join(changed))
    print(f"Verified {len(provenance['files'])} immutable files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify() if args.verify else snapshot()

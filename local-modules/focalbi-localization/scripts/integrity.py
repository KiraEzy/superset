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
"""Reject activation when pinned native sources or baseline copies changed."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--with-rendering", action="store_true")
args = parser.parse_args()
compatibility = json.loads((root / "compatibility.json").read_text())
for path, expected in compatibility["files"].items():
    actual = hashlib.sha256(
        (root.parents[1] / "superset-frontend" / path).read_bytes()
    ).hexdigest()
    if actual != expected:
        raise RuntimeError(f"Compatibility review required: {path}")
if args.with_rendering:
    subprocess.run(  # noqa: S603 - fixed module-owned script
        [
            sys.executable,
            str(root.parent / "focalbi-rendering/scripts/snapshot.py"),
            "--verify",
        ],
        check=True,
    )
print(f"Protected native source hashes passed ({len(compatibility['files'])} files)")

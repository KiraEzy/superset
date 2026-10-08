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
"""Build a Superset manifest and package the extension's owned files."""

import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
dist = root / "dist" / "extension"
dist.mkdir(parents=True, exist_ok=True)
shutil.copytree(
    root / "backend" / "src",
    dist / "backend" / "src",
    dirs_exist_ok=True,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
)
for name in ("LICENSE.txt", "NOTICE"):
    # Superset 6.1 accepts only manifest, frontend/dist and backend/src entries.
    shutil.copy2(root / name, dist / "backend" / "src" / name)
    stale = dist / name
    if stale.exists():
        stale.unlink()
config = json.loads((root / "extension.json").read_text())
manifest = {key: value for key, value in config.items() if key != "backend"}
manifest.update(
    id="focalbi.content-localization",
    frontend={
        "remoteEntry": "remoteEntry.js",
        "moduleFederationName": "focalbi_contentLocalization",
    },
    backend={"entrypoint": "focalbi_localization.entrypoint"},
)
(dist / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
with ZipFile(
    root / "dist" / "focalbi.content-localization-1.0.0.supx", "w", ZIP_DEFLATED
) as archive:
    for path in dist.rglob("*"):
        if path.is_file():
            archive.write(path, path.relative_to(dist).as_posix())
print("Built focalbi.content-localization-1.0.0.supx")

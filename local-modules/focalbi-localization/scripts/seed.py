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
"""Apply an operator-authored fixture to discovered resource fields through APIs."""

import argparse
import json
import re
from pathlib import Path

from http_client import Client

parser = argparse.ArgumentParser()
parser.add_argument("fixture", type=Path)
parser.add_argument("--origin", default="http://localhost:8088")
parser.add_argument("--cookie", type=Path, required=True)
args = parser.parse_args()
fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
client = Client(args.origin, args.cookie)
base = "/extensions/focalbi/content-localization/catalog"
identity = client.request(f"{base}/resolve/dashboard/{fixture['dashboardId']}")[
    "result"
]
bundle = client.request(f"{base}/bundle/dashboard/{identity['uuid']}?locale=en")[
    "result"
]
results = []
for resource_key in bundle["resources"]:
    kind, uid = resource_key.split("/")
    catalog = client.request(f"{base}/resource/{kind}/{uid}")["result"]
    entries = dict(catalog["entries"])
    for field in catalog["fields"]:
        values = fixture.get("translations", {}).get(field["source"])
        for rule in fixture.get("fieldRules", []):
            if rule["type"] == kind and re.search(rule["keyPattern"], field["key"]):
                values = rule["values"]
        dictionary = (
            fixture.get("dictionaries", {}).get(field.get("target"), [])
            if field["kind"] == "category"
            else []
        )
        if values or dictionary:
            entries[field["key"]] = {
                "sourceHash": field["sourceHash"],
                "values": {"en": field["source"], **(values or {})}
                if field["kind"] != "category"
                else {},
                "dictionary": dictionary,
            }
    if entries != catalog["entries"]:
        result = client.request(
            f"{base}/resource/{kind}/{uid}",
            {"revision": catalog["revision"], "entries": entries},
            "PUT",
        )["result"]
        results.append(
            {
                "type": kind,
                "uuid": uid,
                "revision": result["revision"],
                "fieldCount": len(entries),
            }
        )
print(json.dumps(results))

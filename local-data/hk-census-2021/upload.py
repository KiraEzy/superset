# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Upload prepared census CSVs through native Superset file ingestion only."""

from __future__ import annotations

import argparse
import csv
import json  # noqa: TID251 -- Standalone uploader does not load the Superset runtime.
import urllib.request
import uuid
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def upload(origin: str, cookie_path: Path) -> list[dict[str, object]]:
    """Use an existing administrator session without printing or storing its token."""
    address = urlsplit(origin)
    if address.scheme not in {"http", "https"} or not address.netloc:
        raise ValueError("Superset origin must use HTTP or HTTPS")
    if address.path not in {"", "/"} or address.query or address.fragment:
        raise ValueError("Pass an origin, not a URL with a path or query")
    origin = origin.rstrip("/")
    cookie = json.loads(cookie_path.read_text(encoding="utf-8-sig"))
    headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
    jar = CookieJar()
    jar.set_cookie(
        Cookie(
            version=0,
            name=cookie["name"],
            value=cookie["value"],
            port=None,
            port_specified=False,
            domain=cookie["domain"],
            domain_specified=False,
            domain_initial_dot=False,
            path=cookie.get("path", "/"),
            path_specified=True,
            secure=cookie.get("secure", False),
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
        )
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(  # noqa: S310 -- Validated HTTP(S) origin.
        f"{origin}/api/v1/security/csrf_token/", headers=headers
    )
    with opener.open(request, timeout=30) as response:
        csrf = json.load(response)["result"]
    results = []
    for table in ["release", "geography", "indicator", "cell"]:
        path = ROOT / "snapshot" / f"hk_census_2021_{table}.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            fieldnames = next(csv.reader(stream))
        types = dict.fromkeys(fieldnames, "string")
        for field in ["census_year", "boundary_year", "category_order"]:
            if field in types:
                types[field] = "int64"
        if "numeric_value" in types:
            types["numeric_value"] = "float64"
        fields = {
            "type": "csv",
            "table_name": path.stem,
            "schema": "public",
            "already_exists": "fail",
            "dataframe_index": "false",
            "header_row": "0",
            "delimiter": ",",
            "column_data_types": json.dumps(types),
        }
        boundary = "CensusUpload" + uuid.uuid4().hex
        chunks = []
        for name, value in fields.items():
            chunks.append(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                    f"\r\n\r\n{value}\r\n"
                ).encode()
            )
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{path.name}"\r\nContent-Type: text/csv\r\n\r\n'
            ).encode()
        )
        chunks.extend([path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()])
        request = urllib.request.Request(  # noqa: S310 -- Validated HTTP(S) origin.
            f"{origin}/api/v1/database/1/upload/",
            data=b"".join(chunks),
            headers={
                **headers,
                "X-CSRFToken": csrf,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Referer": origin,
            },
            method="POST",
        )
        with opener.open(request, timeout=60) as response:
            if not response.headers.get("Content-Type", "").startswith(
                "application/json"
            ):
                raise RuntimeError(
                    f"Upload returned unexpected response: {response.status} "
                    f"{response.url}"
                )
            result = {
                "table": f"public.{path.stem}",
                "status": response.status,
                "result": json.load(response),
            }
        results.append(result)
        print(json.dumps(result), flush=True)
        runtime = ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        (runtime / "upload-results.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--session-cookie", required=True, type=Path)
    args = parser.parse_args()
    upload(args.origin.rstrip("/"), args.session_cookie)

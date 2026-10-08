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
"""Use an existing authorized session for catalog authoring, without printing it."""

import json
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, Request


class Client:
    """Small operator client; authentication remains native Superset."""

    def __init__(self, origin: str, cookie_file: Path) -> None:
        address = urlsplit(origin)
        if (
            address.scheme not in {"http", "https"}
            or address.path not in {"", "/"}
            or address.query
            or address.fragment
        ):
            raise ValueError("Pass a valid HTTP(S) origin")
        self.origin = origin.rstrip("/")
        value = json.loads(cookie_file.read_text(encoding="utf-8-sig"))
        if value["domain"].lstrip(".") != address.hostname:
            raise ValueError("Session cookie must belong to the requested origin")
        jar = CookieJar()
        cookie_domain = (
            "localhost.local" if value["domain"] == "localhost" else value["domain"]
        )
        jar.set_cookie(
            Cookie(
                version=0,
                name=value["name"],
                value=value["value"],
                port=None,
                port_specified=False,
                domain=cookie_domain,
                domain_specified=False,
                domain_initial_dot=False,
                path=value.get("path", "/"),
                path_specified=True,
                secure=value.get("secure", False),
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
        )
        self.opener = build_opener(HTTPCookieProcessor(jar))
        self.csrf = self.request("/api/v1/security/csrf_token/")["result"]

    def request(self, path: str, data: Any = None, method: str = "GET") -> Any:
        """Send same-origin JSON requests; never include cookies in output."""
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only same-origin API paths are permitted")
        headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            headers["X-CSRFToken"] = self.csrf
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(  # noqa: S310 — validated HTTP(S) origin and same-origin path
            self.origin + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        try:
            # The constructor validates the HTTP(S) origin; paths are same-origin.
            with self.opener.open(request, timeout=60) as response:  # noqa: S310
                return json.load(response)
        except HTTPError as error:
            payload = error.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {error.code}: {payload[:500]}") from None

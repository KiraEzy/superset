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
from superset.views.ai.proxy import _sanitize_http_error_body


def test_sanitize_http_error_body_plain_text() -> None:
    assert _sanitize_http_error_body("Invalid API key", 401) == "Invalid API key"


def test_sanitize_http_error_body_html_document() -> None:
    html = (
        "<!DOCTYPE html><html><head><title>404 Not Found</title></head>"
        "<body><h1>Not Found</h1></body></html>"
    )
    message = _sanitize_http_error_body(html, 404)
    assert "404 Not Found" in message
    assert "Not Found" in message
    assert "<html" not in message


def test_sanitize_http_error_body_empty() -> None:
    assert _sanitize_http_error_body("", 502) == "HTTP 502"

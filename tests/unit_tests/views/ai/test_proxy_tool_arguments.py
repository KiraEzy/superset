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
from superset.views.ai.proxy import (
    _normalize_mcp_tool_arguments,
    _resolve_mcp_tool_invocation,
)

LIST_DATASETS_SCHEMA = [
    {
        "name": "list_datasets",
        "inputSchema": {
            "type": "object",
            "required": ["request"],
            "properties": {
                "request": {
                    "type": "object",
                    "properties": {"page_size": {"type": "integer"}},
                }
            },
        },
    }
]


def test_normalize_mcp_tool_arguments_wraps_flat_args() -> None:
    assert _normalize_mcp_tool_arguments(
        LIST_DATASETS_SCHEMA,
        "list_datasets",
        {"page_size": 100},
    ) == {"request": {"page_size": 100}}


def test_normalize_mcp_tool_arguments_keeps_existing_request_wrapper() -> None:
    wrapped = {"request": {"page": 1}}
    assert (
        _normalize_mcp_tool_arguments(
            LIST_DATASETS_SCHEMA,
            "list_datasets",
            wrapped,
        )
        == wrapped
    )


def test_resolve_mcp_tool_invocation_uses_normalized_args_with_proxy() -> None:
    arguments = _normalize_mcp_tool_arguments(
        LIST_DATASETS_SCHEMA,
        "list_datasets",
        {"page_size": 100},
    )
    tool_name, payload = _resolve_mcp_tool_invocation(
        "list_datasets",
        arguments,
        uses_proxy=True,
    )
    assert tool_name == "call_tool"
    assert payload == {
        "name": "list_datasets",
        "arguments": {"request": {"page_size": 100}},
    }

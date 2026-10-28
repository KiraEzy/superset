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
"""Shared fake MCP fixtures for SDK-native behavioral tests."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import types
from pathlib import Path
from typing import Any

from superset.utils import json

PACKAGE = "standalone_ai_runtime"


module = types.ModuleType(PACKAGE)


module.__path__ = [
    str(
        Path(
            os.environ.get(
                "AI_RUNTIME_SOURCE",
                str(Path(str(__import__("superset").__file__)).parent / "ai_runtime"),
            )
        )
    )
]


sys.modules.setdefault(PACKAGE, module)


engine = importlib.import_module(f"{PACKAGE}.engine")


contracts = importlib.import_module(f"{PACKAGE}.contracts")


policy = importlib.import_module(f"{PACKAGE}.policy")


mcp = importlib.import_module(f"{PACKAGE}.mcp")


providers = importlib.import_module(f"{PACKAGE}.providers")


class Pool:
    def __init__(
        self, tools: list[Any], checkpoints: list[Any], *, fail: bool = False
    ) -> None:
        self.tools, self.checkpoints, self.fail = tools, checkpoints, fail
        self.invocations: list[Any] = []
        self.active = 0
        self.peak = 0

    async def __aenter__(self) -> Any:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def discover(self, connections: Any, refresh_auth: Any) -> Any:
        return self.tools

    async def call(self, tool: Any, arguments: Any) -> Any:
        assert any(
            record.get("status") == "in_progress"
            for record in self.checkpoints[-1]["calls"].values()
        )
        self.invocations.append((tool.name, arguments))
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        if self.fail:
            raise OSError("private upstream body must not escape")
        return {
            "isError": False,
            "content": [],
            "structuredContent": {"success": True, "rows": [{"id": 9}]},
        }


def tool(name: str = "get_data", effect: str = "read", focal: bool = False) -> Any:
    return contracts.Tool(
        name,
        name,
        {"id": "c", "is_focal": focal, "url": "https://example.org/mcp"},
        {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        effect=effect,
    )


def call(name: str = "get_data", identifier: str = "call-1", args: Any = None) -> Any:
    return {
        "id": identifier,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args or {"id": 9})},
    }

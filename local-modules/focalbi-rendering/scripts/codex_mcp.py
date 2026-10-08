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
"""Use the installed Codex app-server and its configured, authenticated MCP."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path


class CodexMCP:
    """Access configured MCP tools through the installed native Codex runtime."""

    def __init__(self, server: str = "focalbi") -> None:
        """Start an ephemeral app-server thread and inspect configured MCP status."""
        binaries = sorted(
            (Path.home() / "AppData/Local/OpenAI/Codex/bin").glob("*/codex.exe"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not binaries:
            raise RuntimeError("Installed Codex executable not found")
        self.server_name = server
        self.messages: queue.Queue = queue.Queue()
        self.counter = 0
        self.process = subprocess.Popen(  # noqa: S603 - installed Codex binary, no shell
            [str(binaries[0]), "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(target=self._read, daemon=True).start()
        self.rpc(
            "initialize",
            {
                "clientInfo": {"name": "focalbi-rendering", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.process.stdin.write(
            json.dumps({"method": "initialized", "params": {}}) + "\n"
        )
        self.process.stdin.flush()
        self.thread_id = self.rpc(
            "thread/start", {"cwd": str(Path.cwd()), "ephemeral": True}
        )["thread"]["id"]
        status = self.rpc(
            "mcpServerStatus/list",
            {"threadId": self.thread_id, "detail": "toolsAndAuthOnly"},
        )
        self.server = next(item for item in status["data"] if item["name"] == server)
        if self.server.get("toolsError"):
            raise RuntimeError(self.server["toolsError"])
        print(
            f"Codex native MCP: {server}, {self.server.get('runtimeStatus')}, "
            f"{len(self.server['tools'])} tools",
            flush=True,
        )

    def _read(self) -> None:
        """Queue app-server protocol messages without exposing credentials."""
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                pass

    def rpc(self, method: str, params: dict) -> dict:
        """Await the response matching a sequential native app-server request."""
        self.counter += 1
        ident = self.counter
        self.process.stdin.write(
            json.dumps({"id": ident, "method": method, "params": params}) + "\n"
        )
        self.process.stdin.flush()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            message = self.messages.get(timeout=max(1, deadline - time.monotonic()))
            if message.get("id") == ident and "method" not in message:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]
        raise TimeoutError(method)

    def call(self, tool: str, request: dict) -> dict:
        """Call a configured MCP tool and normalize its result or reported error."""
        arguments = {"request": request}
        if tool in self.server["tools"] and "request" not in self.server["tools"][tool][
            "inputSchema"
        ].get("properties", {}):
            arguments = request
        if tool not in self.server["tools"] and "call_tool" in self.server["tools"]:
            arguments = {"name": tool, "arguments": arguments}
            tool = "call_tool"
        result = self.rpc(
            "mcpServer/tool/call",
            {
                "threadId": self.thread_id,
                "server": self.server_name,
                "tool": tool,
                "arguments": arguments,
            },
        )
        if result.get("isError"):
            raise RuntimeError(result)
        if result.get("structuredContent"):
            return result["structuredContent"]
        content = next(c["text"] for c in result["content"] if c["type"] == "text")
        if content.startswith("Error:"):
            raise RuntimeError(content)
        try:
            return json.loads(content)
        except ValueError:
            return {"message": content}

    def close(self) -> None:
        """Stop the private app-server process after provisioning or inspection."""
        self.process.terminate()
        self.process.wait(timeout=15)

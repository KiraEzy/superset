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
"""Opt-in live release evaluation. Creates only tagged Chat test conversations.

Run inside the Chat web environment with AI_CHAT_RUNTIME_ENABLED=true and a
configured model. Uses native permissions and the unchanged MCP endpoint.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import requests
from flask_appbuilder.security.sqla.models import User

from superset.app import create_app
from superset.extensions import db

TARGET = os.environ.get("AI_EVAL_URL", "http://localhost:8088")
REPORT = os.environ.get("AI_EVAL_REPORT", "/tmp/focal-ai-live-report.json")


def main() -> None:
    """Exercise real HTTP acceptance, replay and model/tool completion."""
    app = create_app()
    with app.app_context():
        from superset import security_manager

        actor = db.session.query(User).filter_by(username="admin", active=True).one()
        post = security_manager.get_user_posts(actor)[0]
        signed = app.session_interface.get_signing_serializer(app).dumps(
            {"_user_id": str(actor.id), "_fresh": True, "active_post_id": post.id}
        )

    def client() -> requests.Session:
        session = requests.Session()
        session.cookies.set(app.config.get("SESSION_COOKIE_NAME", "session"), signed)
        response = session.get(TARGET + "/api/v1/security/csrf_token/", timeout=30)
        response.raise_for_status()
        session.headers["X-CSRFToken"] = response.json()["result"]
        # Remove the domainless bootstrap cookie; the server's Set-Cookie now
        # carries the CSRF session value and must be the sole session cookie.
        session.cookies.clear(
            domain="", path="/", name=app.config.get("SESSION_COOKIE_NAME", "session")
        )
        return session

    def post_json(session: requests.Session, path: str, data: dict) -> dict:
        response = session.post(TARGET + path, json=data, timeout=30)
        if response.status_code >= 300:
            raise RuntimeError(
                f"API {path}: HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.json().get("result", response.json())

    def scenario(prompt: str) -> dict:
        session = client()
        thread = post_json(
            session, "/api/v1/ai_chat_session/", {"title": "AI runtime evaluation"}
        )
        identifier = thread["uuid"]
        payload = {
            "input": prompt,
            "connection_ids": ["focalbi"],
            "workflow_ids": [],
            "context": [],
            "idempotency_key": str(uuid4()),
        }
        start = time.monotonic()
        turn = post_json(session, f"/api/v1/ai/threads/{identifier}/turns", payload)
        accepted = time.monotonic() - start
        repeat = post_json(session, f"/api/v1/ai/threads/{identifier}/turns", payload)
        assert turn["id"] == repeat["id"], "Duplicate submission created another turn"
        deadline = time.monotonic() + 480
        first_event = None
        while time.monotonic() < deadline:
            response = session.get(
                TARGET + f"/api/v1/ai/turns/{turn['id']}", timeout=30
            )
            response.raise_for_status()
            turn = response.json()["result"]
            if first_event is None and turn["last_sequence"] > 1:
                first_event = time.monotonic() - start
            if turn["status"] in {
                "completed",
                "failed",
                "cancelled",
                "waiting_input",
                "waiting_approval",
                "needs_review",
            }:
                break
            time.sleep(0.5)
        # A fresh client simulates a disconnected page with no local transcript.
        reloaded = (
            client()
            .get(TARGET + f"/api/v1/ai/turns/{turn['id']}", timeout=30)
            .json()["result"]
        )
        assert (
            reloaded["id"] == turn["id"]
            and reloaded["last_sequence"] >= turn["last_sequence"]
        )
        events = session.get(
            TARGET + f"/api/v1/ai/turns/{turn['id']}/events?after=0",
            stream=True,
            timeout=30,
        )
        event_start = time.monotonic()
        seen = []
        for line in events.iter_lines(chunk_size=1, decode_unicode=True):
            if line.startswith("data:"):
                seen.append(json.loads(line[5:]))
            if seen and (
                seen[-1]["type"] in {"turn_completed", "turn_failed"}
                or time.monotonic() - event_start > 3
            ):
                break
        events.close()
        assert seen and seen[0]["sequence"] == 1, "Missing database event replay"
        result = {
            "prompt": prompt,
            "thread_id": identifier,
            "turn_id": turn["id"],
            "status": turn["status"],
            "accept_seconds": accepted,
            "event_read_seconds": time.monotonic() - event_start,
            "items": len(turn["items"]),
            "artifacts": len(turn["artifacts"]),
            "replayed_events": len(seen),
            "error": turn.get("error"),
            "content": turn.get("content", ""),
        }
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in ("turn_id", "status", "items", "artifacts", "error")
                }
            ),
            flush=True,
        )
        return result

    prompts = [
        "Check the Focal BI connection health and tell me the result.",
        "List the available datasets. Give dataset IDs and names.",
        "Find chart 119 and explain its dataset, metrics and dimensions. Do not change it.",
        "List available dashboards with IDs and titles. Do not change them.",
        "Inspect dataset 1 and explain its columns and metrics. If it does not exist, explain that.",
        "Find chart 119 and show its preview. Do not save or change it.",
        "List the databases available to my active post.",
        "Find chart 119 and show its configuration, preserving the IDs. Do not change it.",
        "List datasets related to revenue. If none exists, say so based on the tool evidence.",
        "Find dashboard 1 and explain its charts. If unavailable, report it without inventing data.",
    ]
    prompts = prompts[: int(os.environ.get("AI_EVAL_LIMIT", len(prompts)))]
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(scenario, prompts))
    success = sum(row["status"] == "completed" and row["items"] >= 2 for row in results)
    report = {
        "model": "deepseek-v4-pro",
        "successes": success,
        "total": len(results),
        "success_rate": success / len(results),
        "concurrency": 5,
        "accept_p95_seconds": sorted(row["accept_seconds"] for row in results)[-1],
        "replay_p95_seconds": sorted(row["event_read_seconds"] for row in results)[-1],
        "results": results,
    }
    Path(REPORT).write_text(json.dumps(report, indent=2))
    print(
        json.dumps({key: value for key, value in report.items() if key != "results"}),
        flush=True,
    )


if __name__ == "__main__":
    main()

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
"""Opt-in five-turn SSE visibility and reconnect workload against the Chat web."""

import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests
from flask_appbuilder.security.sqla.models import User
from superset.app import create_app
from superset.extensions import db


def main():
    app = create_app()
    target = os.environ.get("AI_EVAL_URL", "http://superset:8088")
    with app.app_context():
        from superset import security_manager

        actor = db.session.query(User).filter_by(username="admin", active=True).one()
        post = security_manager.get_user_posts(actor)[0]
        name = app.config.get("SESSION_COOKIE_NAME", "session")
        signed = app.session_interface.get_signing_serializer(app).dumps(
            {"_user_id": str(actor.id), "_fresh": True, "active_post_id": post.id}
        )

    def measure(index):
        client = requests.Session()
        client.cookies.set(name, signed)
        response = client.get(target + "/api/v1/security/csrf_token/", timeout=30)
        response.raise_for_status()
        client.headers["X-CSRFToken"] = response.json()["result"]
        client.cookies.clear(domain="", path="/", name=name)

        def post_json(path, payload):
            response = client.post(target + path, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()["result"]

        thread = post_json("/api/v1/ai_chat_session/", {"title": "Stream latency QA"})[
            "uuid"
        ]
        started = time.monotonic()
        turn = post_json(
            f"/api/v1/ai/threads/{thread}/turns",
            {
                "input": "Check Focal BI connection health with health_check. Reply with one short status.",
                "idempotency_key": str(uuid4()),
                "connection_ids": ["focalbi"],
                "workflow_ids": [],
                "context": [],
            },
        )
        accepted = time.monotonic() - started
        cursor, forced_reconnect = 0, False
        latency = []
        terminal = None
        deadline = time.monotonic() + 240
        while not terminal and time.monotonic() < deadline:
            # Keep the original URL cursor: Last-Event-ID must take precedence
            # during browser-native reconnection.
            with client.get(
                target + f"/api/v1/ai/turns/{turn['id']}/events?after=0",
                headers={"Last-Event-ID": str(cursor)},
                stream=True,
                timeout=(15, 35),
            ) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines(chunk_size=1, decode_unicode=True):
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:])
                    assert event["sequence"] == cursor + 1, (
                        "Replay duplicated or skipped an event"
                    )
                    cursor = event["sequence"]
                    created = datetime.fromisoformat(
                        event["timestamp"].replace("Z", "+00:00")
                    )
                    latency.append(
                        (datetime.now(timezone.utc) - created).total_seconds()
                    )
                    if event["type"] in {"turn_completed", "turn_failed"}:
                        terminal = event["payload"]["status"]
                        break
                    if not forced_reconnect:
                        forced_reconnect = True
                        break
        assert terminal == "completed", (turn["id"], terminal)
        return {
            "turn_id": turn["id"],
            "thread_id": thread,
            "accept_seconds": accepted,
            "event_latencies": latency,
            "events": cursor,
            "reconnected": forced_reconnect,
        }

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(measure, range(5)))
    latencies = sorted(value for row in results for value in row["event_latencies"])
    report = {
        "concurrency": 5,
        "turns_completed": len(results),
        "accept_p95_seconds": max(row["accept_seconds"] for row in results),
        "event_visibility_p95_seconds": latencies[math.ceil(len(latencies) * 0.95) - 1],
        "event_samples": len(latencies),
        "all_reconnected": all(row["reconnected"] for row in results),
        "results": results,
    }
    Path("/tmp/focal-ai-stream-load.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "results"}), flush=True)


if __name__ == "__main__":
    main()

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
"""Opt-in real-provider preview/save/edit evaluation using one dedicated chart."""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import requests
from flask_appbuilder.security.sqla.models import User
from superset.app import create_app
from superset.extensions import db


def main():
    app = create_app()
    target = os.environ.get("AI_EVAL_URL", "http://localhost:8088")
    with app.app_context():
        from superset import security_manager

        actor = db.session.query(User).filter_by(username="admin", active=True).one()
        post = security_manager.get_user_posts(actor)[0]
        cookie = app.session_interface.get_signing_serializer(app).dumps(
            {"_user_id": str(actor.id), "_fresh": True, "active_post_id": post.id}
        )
    client = requests.Session()
    cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
    client.cookies.set(cookie_name, cookie)
    csrf = client.get(target + "/api/v1/security/csrf_token/").json()["result"]
    client.cookies.clear(domain="", path="/", name=cookie_name)
    client.headers["X-CSRFToken"] = csrf

    def post_json(path, payload):
        response = client.post(target + path, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()["result"]

    title = "AI Runtime Evaluation " + str(uuid4())[:8]
    thread = post_json("/api/v1/ai_chat_session/", {"title": title})["uuid"]

    def turn(prompt):
        payload = {
            "input": prompt,
            "connection_ids": ["focalbi"],
            "workflow_ids": [],
            "context": [],
            "idempotency_key": str(uuid4()),
        }
        result = post_json(f"/api/v1/ai/threads/{thread}/turns", payload)
        repeated = post_json(f"/api/v1/ai/threads/{thread}/turns", payload)
        assert result["id"] == repeated["id"]
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            result = client.get(
                target + f"/api/v1/ai/turns/{result['id']}", timeout=30
            ).json()["result"]
            if result["status"] in {
                "completed",
                "failed",
                "waiting_approval",
                "waiting_input",
                "needs_review",
            }:
                break
            time.sleep(0.5)
        print(
            json.dumps(
                {
                    "turn_id": result["id"],
                    "status": result["status"],
                    "artifacts": result["artifacts"],
                    "pending_requests": result["pending_requests"],
                    "error": result.get("error"),
                }
            ),
            flush=True,
        )
        return result

    preview = turn(
        f"Create a table chart preview from dataset 1 with the name and color columns. Title it '{title}'. Do not save it. Use generate_chart."
    )
    assert preview["status"] == "completed"
    assert any(
        item["type"] == "chart" and not item["saved"] for item in preview["artifacts"]
    )
    saved = turn(
        "Save this chart exactly as previewed, keeping the title, columns and all filters unchanged."
    )
    assert saved["status"] == "completed"
    chart_ids = [
        item["payload"].get("slice_id", item["payload"].get("id"))
        for item in saved["artifacts"]
        if item["type"] == "chart" and item["saved"]
    ]
    chart_id = next(identifier for identifier in chart_ids if identifier)
    edited = turn(
        f"Update chart {chart_id}: rename it to '{title} updated'. Apply and save the edit, not just a preview. Keep the columns, data and all filters unchanged."
    )
    assert edited["status"] == "completed"
    report = {
        "thread_id": thread,
        "chart_id": chart_id,
        "title": title,
        "preview_turn": preview["id"],
        "save_turn": saved["id"],
        "edit_turn": edited["id"],
        "success": True,
        "cleanup": "Dedicated evaluation chart retained for inspection",
    }
    Path("/tmp/focal-ai-artifact-flow.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()

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
"""Opt-in persisted SDK evaluation using configured published models.

Run on the Chat worker with requirements/ai-agents.txt installed. Creates tagged
Chat conversations and unsaved previews only. Does not change the rollout default
or connection settings, and does not print credentials or canonical model input.
"""

import asyncio
import hashlib
import os
import time
from pathlib import Path
from uuid import uuid4

from flask import g

from superset.app import create_app
from superset.utils import json


def main() -> None:  # noqa: C901
    app = create_app()
    app.config["AI_RUNTIME_MAX_ROUNDS"] = 16
    app.config["AI_RUNTIME_MAX_ACTIVE_SECONDS"] = 420
    report = []
    with app.app_context():
        from flask_appbuilder.security.sqla.models import User

        from superset import security_manager
        from superset.ai_runtime import model_catalog, runner, store
        from superset.extensions import db
        from superset.models.ai_chat import AiChatSession
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        def connection_fingerprints() -> dict[str, str]:
            from sqlalchemy import select

            from superset.models.ai_chat import AiConnectionConfig
            from superset.models.ai_model_catalog import AiModel, AiModelConnection
            from superset.models.ai_runtime_connections import (
                AiRuntimeAccount,
                AiRuntimeConnection,
            )

            protected = (
                AiModelConnection,
                AiModel,
                AiConnectionConfig,
                AiRuntimeConnection,
                AiRuntimeAccount,
            )
            return {
                model.__tablename__: hashlib.sha256(
                    repr(
                        [
                            tuple(
                                bytes(value) if isinstance(value, memoryview) else value
                                for value in row
                            )
                            for row in db.session.execute(
                                select(model.__table__).order_by(model.id)
                            ).all()
                        ]
                    ).encode()
                ).hexdigest()
                for model in protected
            }

        actor = db.session.query(User).filter_by(username="admin", active=True).one()
        post = security_manager.get_user_posts(actor)[0]
        before = [db.session.query(Slice).count(), db.session.query(Dashboard).count()]
        protected_before = connection_fingerprints()
        models = [
            m
            for m in model_catalog.catalogue()["models"]
            if m["connection"].lower() in {"gpustack", "deepseek"}
        ]
        requested = os.environ.get("AI_SDK_EVAL_CONNECTION", "").lower()
        if requested:
            models = [m for m in models if m["connection"].lower() == requested]
        assert models, "No matching published models"
        for model in models:
            with app.test_request_context():
                g.user = actor
                g.mcp_active_post_id = post.id
                thread = AiChatSession(
                    title=f"SDK validation {model['connection']} {uuid4().hex[:8]}",
                    post_id=post.id,
                    runtime_version=2,
                    created_by_fk=actor.id,
                    changed_by_fk=actor.id,
                )
                db.session.add(thread)
                db.session.commit()
                prompts = [
                    "What datasets can I use? Show a short first page only.",
                    "Use hk_census_2021_geography to preview one vertical bar chart "
                    "of COUNT(*) by region. Inspect its schema first. Do not save "
                    "or modify any saved resources.",
                    "Change the bar chart you just previewed to horizontal bars. "
                    "Keep the same dataset, metric and filters. "
                    "Preview only; do not save.",
                ]
                if os.environ.get("AI_SDK_EVAL_PROMPTS"):
                    prompts = json.loads(os.environ["AI_SDK_EVAL_PROMPTS"])
                for prompt_index, prompt in enumerate(prompts):
                    if (
                        os.environ.get("AI_SDK_EVAL_COMPACTION") == "1"
                        and prompt_index == 2
                    ):
                        from superset.ai_runtime.native_session import (
                            application_models,
                            FocalSession,
                        )

                        session_model, _ = application_models()
                        sdk_row = (
                            db.session.query(session_model)
                            .filter_by(id=str(thread.uuid))
                            .one()
                        )
                        sdk_session = FocalSession(
                            str(thread.uuid),
                            database=db.session,
                            models=application_models(),
                            owner_id=actor.id,
                            post_id=post.id,
                            binding=sdk_row.binding,
                            turn_id=str(uuid4()),
                            guard=lambda: None,
                        )
                        # Completed synthetic exchanges force context pressure in this
                        # isolated evaluation chat without changing provider settings.
                        padding = []
                        for index in range(6):
                            padding.extend(
                                [
                                    {
                                        "role": "user",
                                        "content": (
                                            "Validation-only historical notes; keep "
                                            "the chart dataset, metric "
                                            "and filters unchanged. "
                                        )
                                        + (f"Historical note {index}. " * 280),
                                    },
                                    {
                                        "role": "assistant",
                                        "content": (
                                            "Recorded. No tools or writes executed."
                                        ),
                                    },
                                ]
                            )
                        asyncio.run(sdk_session.add_items(padding))
                    turn = store.submit(
                        str(thread.uuid),
                        {
                            "input": prompt,
                            "model_id": model["id"],
                            "idempotency_key": str(uuid4()),
                            "context": [],
                        },
                    )
                    identifier = turn.id
                    if (
                        os.environ.get("AI_SDK_EVAL_COMPACTION") == "1"
                        and prompt_index == 2
                    ):
                        accepted = store.loads(turn.state_json)
                        accepted["budgets"]["context_window_tokens"] = 32768
                        turn.state_json = store.dumps(accepted)
                        db.session.commit()
                    if os.environ.get("AI_SDK_EVAL_THINKING") == "off":
                        accepted = store.loads(turn.state_json)
                        accepted["_native_thinking"] = False
                        turn.state_json = store.dumps(accepted)
                        db.session.commit()
                    started = time.monotonic()
                    if os.environ.get("AI_SDK_EVAL_WORKER") == "1":
                        while time.monotonic() - started < 480:
                            db.session.refresh(turn)
                            if turn.status not in {"queued", "running"}:
                                break
                            time.sleep(0.5)
                    else:
                        runner.execute_turn(identifier)
                    db.session.expire_all()
                    turn = store.get_turn(identifier)
                    state = store.loads(turn.state_json)
                    cp = state.get("checkpoint", {})
                    entry = {
                        "connection": model["connection"],
                        "model": model["name"],
                        "thread_id": str(thread.uuid),
                        "turn_id": turn.id,
                        "prompt": prompt,
                        "status": turn.status,
                        "seconds": round(time.monotonic() - started, 2),
                        "execution_engine": state.get("execution_engine"),
                        "error": store.loads(turn.error_json),
                        "tools": cp.get("tools_used", []),
                        "usage": cp.get("usage", {}),
                        "artifacts": [
                            {
                                "type": a["type"],
                                "title": a.get("title"),
                                "saved": a.get("saved"),
                                "payload": a.get("payload", {}),
                            }
                            for a in store.snapshot(turn)["artifacts"]
                        ],
                        "answer": turn.content,
                    }
                    report.append(entry)
                    if (
                        os.environ.get("AI_SDK_EVAL_COMPACTION") == "1"
                        and prompt_index == 2
                    ):
                        from sqlalchemy import text

                        from superset.ai_runtime.native_session import (
                            application_models,
                        )

                        summary_model = application_models()[0].summary_model
                        summary = (
                            db.session.query(summary_model)
                            .filter_by(session_id=str(thread.uuid))
                            .one_or_none()
                        )
                        entry["compaction_boundary"] = (
                            summary.boundary if summary else None
                        )
                        raw = db.session.execute(
                            text(
                                "SELECT payload FROM ai_sdk_summary "
                                "WHERE session_id=:id"
                            ),
                            {"id": str(thread.uuid)},
                        ).scalar()
                        entry["summary_encrypted"] = isinstance(
                            raw, (bytes, memoryview)
                        ) and b'"summary"' not in bytes(raw)

                    Path(
                        os.environ.get(
                            "AI_SDK_EVAL_REPORT",
                            str(Path.cwd() / "agents-live-report.json"),
                        )
                    ).write_text(json.dumps(report, indent=2))
                    print(
                        json.dumps(
                            {
                                k: entry[k]
                                for k in [
                                    "connection",
                                    "turn_id",
                                    "status",
                                    "seconds",
                                    "error",
                                ]
                            }
                        ),
                        flush=True,
                    )
                    if turn.status != "completed":
                        break
                if len(prompts) == 3 and not os.environ.get("AI_SDK_EVAL_PROMPTS"):
                    latest = report[-3:]
                    assert all(row["status"] == "completed" for row in latest)
                    if os.environ.get("AI_SDK_EVAL_COMPACTION") == "1":
                        assert latest[-1]["compaction_boundary"]
                        assert latest[-1]["summary_encrypted"]
                    charts = [
                        [a for a in row["artifacts"] if a["type"] == "chart"]
                        for row in latest[1:]
                    ]
                    assert all(charts), "Creation and edit must each produce a chart"
                    first, changed = [
                        items[-1]["payload"]["form_data"] for items in charts
                    ]
                    assert changed.get("orientation") == "horizontal"
                    for field in ("datasource", "metrics", "adhoc_filters", "x_axis"):
                        assert first.get(field) == changed.get(field), field
        after = [db.session.query(Slice).count(), db.session.query(Dashboard).count()]
        assert before == after, "Preview validation changed saved resource counts"
        assert protected_before == connection_fingerprints(), (
            "Connection settings changed"
        )
        print(
            json.dumps(
                {
                    "saved_resources_before": before,
                    "saved_resources_after": after,
                    "connection_settings_unchanged": True,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()

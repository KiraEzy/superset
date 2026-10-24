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
"""Scoped legacy test-data cleanup and operator diagnostics for AI Chat."""

from pathlib import Path

import click
from flask.cli import with_appcontext

from superset.extensions import db
from superset.utils import json


@click.group("ai-runtime")
def ai_runtime() -> None:
    """Manage the Chat runtime independently of the MCP server."""


@ai_runtime.command("capture-legacy")
@click.option("--output", type=click.Path(dir_okay=False), required=True)
@with_appcontext
def capture_legacy(output: str) -> None:
    """Capture an explicit legacy ID set before rollout; no transcript export."""
    from superset.models.ai_chat import AiChatSession

    rows = (
        db.session.query(AiChatSession).filter(AiChatSession.runtime_version == 1).all()
    )
    data = {
        "session_ids": [r.id for r in rows],
        "session_uuids": {str(r.id): str(r.uuid) for r in rows},
        "count": len(rows),
    }
    Path(output).write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(f"Captured {len(rows)} legacy session IDs")


@ai_runtime.command("purge-legacy")
@click.option("--manifest", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option(
    "--apply", is_flag=True, help="Delete only matching captured legacy sessions"
)
@with_appcontext
def purge_legacy(manifest: str, apply: bool) -> None:
    """Validate captured IDs and runtime versions before scoped deletion."""
    from superset.models.ai_chat import AiChatSession

    data = json.loads(Path(manifest).read_text(encoding="utf-8-sig"))
    ids = data.get("session_ids")
    if not isinstance(ids, list) or any(
        isinstance(i, bool) or not isinstance(i, int) for i in ids
    ):
        raise click.ClickException("Manifest must contain integer session IDs")
    rows = (
        db.session.query(AiChatSession)
        .filter(AiChatSession.id.in_(ids), AiChatSession.runtime_version == 1)
        .with_for_update()
        .all()
    )
    expected = data.get("session_uuids", {})
    if rows and (
        not expected or any(expected.get(str(r.id)) != str(r.uuid) for r in rows)
    ):
        raise click.ClickException(
            "Manifest UUIDs must match every selected legacy session"
        )
    count = len(rows)
    if apply:
        for row in rows:
            db.session.delete(row)
        db.session.commit()
    click.echo(
        f"{'Deleted' if apply else 'Would delete'} {count} legacy sessions; "
        "BI resources and connection settings untouched"
    )

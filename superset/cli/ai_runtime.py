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
"""Manifest-bound offline conversation reset for SDK-native AI Chat."""

from pathlib import Path

import click
from flask.cli import with_appcontext

from superset.extensions import db
from superset.utils import json


@click.group("ai-runtime")
def ai_runtime() -> None:
    """Manage the Chat runtime independently of the MCP server."""


@ai_runtime.command("capture-reset")
@click.option("--output", type=click.Path(dir_okay=False), required=True)
@with_appcontext
def capture_reset(output: str) -> None:
    """Capture all disposable chat history for an offline SDK cutover."""
    from superset.ai_runtime.reset import inventory

    data = inventory(db.session.connection())
    Path(output).write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(json.dumps(data["conversations"]))


@ai_runtime.command("reset-conversations")
@click.option("--manifest", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--apply", is_flag=True)
@with_appcontext
def reset_conversations(manifest: str, apply: bool) -> None:
    """Reset only captured conversations after offline backup and quiescence."""
    from superset.ai_runtime.reset import inventory, reset
    from superset.ai_runtime.store import loads
    from superset.models.ai_runtime import AiRuntimeTurn

    for turn in db.session.query(AiRuntimeTurn).filter(
        AiRuntimeTurn.active_key.isnot(None)
    ):
        if turn.lease_owner or any(
            item.get("effect") != "read" and item.get("status") == "in_progress"
            for item in loads(turn.state_json)
            .get("checkpoint", {})
            .get("calls", {})
            .values()
        ):
            raise click.ClickException(
                "Settle leased or uncertain operations before resetting"
            )
    data = json.loads(Path(manifest).read_text(encoding="utf-8-sig"))
    try:
        if apply:
            reset(db.session.connection(), data)
            db.session.commit()
        elif inventory(db.session.connection()) != data:
            raise ValueError("Reset inventory changed")
    except ValueError as ex:
        db.session.rollback()
        raise click.ClickException(str(ex)) from ex
    click.echo(
        "Deleted captured conversations"
        if apply
        else "Reset inventory verified; no deletion performed"
    )

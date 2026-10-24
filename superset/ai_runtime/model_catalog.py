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
"""Revision-bound discovery, capability probes, publication and model routing."""

from __future__ import annotations

import base64
import io
import re
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import requests
from PIL import Image

from superset.constants import PASSWORD_MASK
from superset.extensions import db
from superset.models.ai_model_catalog import (
    AiModel,
    AiModelConnection,
    AiModelVerification,
)
from superset.utils import json
from superset.views.ai import config_store
from superset.views.ai.proxy import normalize_llm_base_url


def bootstrap() -> None:
    """Convert saved provider entries once, preserving the active legacy model."""
    if db.session.query(AiModelConnection).first():
        return
    from superset.models.ai_chat import AiConnectionConfig

    db.session.query(AiConnectionConfig).filter_by(
        id=config_store.CONFIG_ID
    ).with_for_update().first()
    if db.session.query(AiModelConnection).first():
        return
    state = config_store.load_stored_state()
    active = config_store.resolve_active_config()
    for provider, fields in state.get("providerSettings", {}).items():
        if not fields.get("llmApiBaseUrl") or not fields.get("llmModel"):
            continue
        config = {
            **fields,
            "llmProvider": provider,
            "llmAdapter": state.get("llmAdapter", "chat_completions")
            if provider == "openai"
            else "chat_completions",
        }
        conn = AiModelConnection(label=provider.title(), config_json=json.dumps(config))
        db.session.add(conn)
        db.session.flush()
        is_active = provider == active.get("llmProvider")
        db.session.add(
            AiModel(
                connection_id=conn.id,
                model_name=fields["llmModel"],
                revision=1,
                status="legacy" if is_active else "discovered",
                position=0 if is_active else None,
                is_default=is_active,
            )
        )
    db.session.commit()


def catalogue(*, admin: bool = False) -> dict[str, Any]:
    """Return sanitized models; endpoint and credential data is admin-only."""
    bootstrap()
    connections = {c.id: c for c in db.session.query(AiModelConnection).all()}
    models = []
    for model in (
        db.session.query(AiModel).order_by(AiModel.position, AiModel.model_name).all()
    ):
        conn = connections[model.connection_id]
        ready = (
            model.available
            and model.revision == conn.revision
            and (
                model.status == "verified"
                or (model.status == "legacy" and model.position is not None)
            )
        )
        if not admin and (not ready or model.position is None):
            continue
        value = {
            "id": model.id,
            "name": model.model_name,
            "connection": conn.label,
            "vision": model.vision,
            "default": model.is_default,
        }
        if admin:
            value.update(
                connection_id=conn.id,
                status=model.status if model.available else "unavailable",
                ready=ready,
                published=model.position is not None,
                position=model.position,
            )
        models.append(value)
    result: dict[str, Any] = {"models": models}
    if admin:
        result["connections"] = [
            {
                "id": c.id,
                "label": c.label,
                "revision": c.revision,
                "config": {
                    **json.loads(c.config_json),
                    "llmApiKey": PASSWORD_MASK
                    if json.loads(c.config_json).get("llmApiKey")
                    else "",
                },
            }
            for c in connections.values()
        ]
    return result


def resolve(model_id: str | None, base: dict[str, Any]) -> dict[str, Any]:
    """Resolve a published identity to a private immutable turn configuration."""
    if model_id is not None and not isinstance(model_id, str):
        raise ValueError("Choose an available model")
    # Legacy callers continue to use the configured model until the catalogue exists.
    if model_id is None:
        selected = db.session.query(AiModel).filter_by(is_default=True).first()
        if selected is None:
            return base
    else:
        selected = db.session.query(AiModel).filter_by(id=model_id).first()
    conn = (
        db.session.query(AiModelConnection).get(selected.connection_id)
        if selected
        else None
    )
    if (
        not selected
        or not conn
        or selected.position is None
        or not selected.available
        or selected.revision != conn.revision
        or selected.status not in {"verified", "legacy"}
    ):
        raise ValueError("Choose an available model")
    return {
        **base,
        **json.loads(conn.config_json),
        "llmModel": selected.model_name,
        "model_id": selected.id,
        "model_connection_id": conn.id,
        "model_revision": conn.revision,
        "vision": selected.vision,
    }


def save_reasoning_visibility(connection_id: str, enabled: Any) -> None:
    """Save a display preference without changing credentials or capabilities."""
    if not isinstance(enabled, bool):
        raise ValueError("showModelReasoning must be a boolean")
    conn = (
        db.session.query(AiModelConnection)
        .filter_by(id=connection_id)
        .with_for_update()
        .one_or_none()
    )
    if conn is None:
        raise ValueError("Connection not found")
    if (
        db.session.query(AiModelVerification)
        .filter(
            AiModelVerification.connection_id == connection_id,
            AiModelVerification.status.in_(["queued", "running"]),
        )
        .first()
    ):
        raise ValueError(
            "Wait for connection verification before changing reasoning display"
        )
    config = json.loads(conn.config_json)
    if enabled and config.get("llmProvider") not in {"custom", "lmstudio"}:
        raise ValueError(
            "Model reasoning display is supported only for "
            "self-hosted compatible connections"
        )
    config["showModelReasoning"] = enabled
    conn.config_json = json.dumps(config)
    db.session.commit()


def queue_connection(data: dict[str, Any]) -> str:  # noqa: C901 - validated connection candidate
    """Validate a candidate without changing the last working connection."""
    config = data.get("config")
    if not isinstance(config, dict):
        raise ValueError("Connection configuration is required")
    label = str(data.get("label", "")).strip()
    if not label or len(label) > 128:
        raise ValueError("Enter a connection name (1?128 characters)")
    conn = (
        db.session.query(AiModelConnection)
        .filter_by(id=data.get("id"))
        .with_for_update()
        .one_or_none()
        if data.get("id")
        else None
    )
    if data.get("id") and not conn:
        raise ValueError("Connection not found")
    provider = config.get("llmProvider")
    if provider not in config_store.VALID_PROVIDERS:
        raise ValueError("Unknown provider")
    base = normalize_llm_base_url(str(config.get("llmApiBaseUrl", "")))
    if not base.startswith(("https://", "http://")) or "@" in base:
        raise ValueError("Enter an HTTP model endpoint without embedded credentials")
    key = config.get("llmApiKey", "")
    if key == PASSWORD_MASK:
        saved = json.loads(conn.config_json) if conn else {}
        if (
            saved.get("llmApiBaseUrl", "").rstrip("/") != base.rstrip("/")
            or saved.get("llmProvider") != provider
        ):
            raise ValueError("Enter a new key when changing the destination")
        key = saved.get("llmApiKey", "")
    adapter = config.get("llmAdapter", "chat_completions")
    if adapter not in {"responses", "chat_completions"} or (
        adapter == "responses" and provider != "openai"
    ):
        raise ValueError("Unsupported model protocol")
    name = config.get("llmModel")
    if not isinstance(name, str) or not name.strip() or len(name) > 256:
        raise ValueError("Enter a test model")
    display = config.get(
        "showModelReasoning",
        json.loads(conn.config_json).get("showModelReasoning", False)
        if conn
        else False,
    )
    if not isinstance(display, bool):
        raise ValueError("showModelReasoning must be a boolean")
    if display and provider not in {"custom", "lmstudio"}:
        raise ValueError(
            "Model reasoning display is supported only for "
            "self-hosted compatible connections"
        )
    candidate = {
        "label": label,
        "config": {
            "llmProvider": provider,
            "llmApiBaseUrl": base,
            "llmApiKey": key,
            "llmModel": name.strip(),
            "llmAdapter": adapter,
            "showModelReasoning": display,
        },
    }
    job = AiModelVerification(
        connection_id=conn.id if conn else str(uuid4()),
        expected_revision=conn.revision if conn else 0,
        candidate_json=json.dumps(candidate),
        kind="connection",
    )
    db.session.add(job)
    db.session.commit()
    return job.id


def queue_model(model_id: str) -> str:
    """Schedule probes on the model's exact connection revision."""
    model = (
        db.session.query(AiModel).filter_by(id=model_id, available=True).one_or_none()
    )
    if not model:
        raise ValueError("Model not found")
    conn = db.session.query(AiModelConnection).get(model.connection_id)
    candidate = {
        "config": {**json.loads(conn.config_json), "llmModel": model.model_name}
    }
    job = AiModelVerification(
        connection_id=conn.id,
        expected_revision=conn.revision,
        candidate_json=json.dumps(candidate),
        kind="model",
        model_id=model.id,
    )
    db.session.add(job)
    db.session.commit()
    return job.id


def publish(ids: list[str], default: str) -> None:
    """Publish one ordered selection atomically; a usable default is mandatory."""
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(i, str) for i in ids)
        or len(ids) != len(set(ids))
        or default not in ids
    ):
        raise ValueError("Select models and a default")
    connections = {
        c.id: c for c in db.session.query(AiModelConnection).with_for_update().all()
    }
    models = db.session.query(AiModel).with_for_update().all()
    ready = {
        m.id
        for m in models
        if m.available
        and m.revision == connections[m.connection_id].revision
        and (
            m.status == "verified" or (m.status == "legacy" and m.position is not None)
        )
    }
    if not set(ids) <= ready:
        raise ValueError("Verify every selected model before publishing")
    for model in models:
        model.position = ids.index(model.id) if model.id in ids else None
        model.is_default = model.id == default
    db.session.commit()


def request_json(
    config: dict[str, Any], path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Bound probes and never follow redirects with a connection credential."""
    headers = (
        {"Authorization": "Bearer " + config["llmApiKey"]}
        if config.get("llmApiKey")
        else {}
    )
    response = requests.request(
        "POST" if body is not None else "GET",
        config["llmApiBaseUrl"].rstrip("/") + path,
        json=body,
        headers=headers,
        timeout=(10, 45),
        allow_redirects=False,
        stream=True,
    )
    try:
        if response.status_code >= 300:
            raise ValueError(f"Provider returned HTTP {response.status_code}")
        raw = bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            if len(raw) > 2_000_000:
                raise ValueError("Provider response exceeded verification limit")
        result = json.loads(bytes(raw))
        if not isinstance(result, dict):
            raise ValueError("Invalid provider response")
        return result
    finally:
        response.close()


def response_text(result: dict[str, Any], responses: bool) -> str:
    """Extract assistant text only, excluding echoed tool arguments and metadata."""
    if responses:
        return " ".join(
            part.get("text", "")
            for item in result.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
    message = result.get("choices", [{}])[0].get("message", {})
    if message.get("tool_calls"):
        return ""
    return message.get("content") or ""


def probe(config: dict[str, Any], *, vision: bool = False) -> None:
    """Test synthetic tool round-trip or a known-color image; never invoke BI."""
    responses = config.get("llmAdapter") == "responses"
    model = config["llmModel"]
    marker = "verified_" + uuid4().hex[:12]
    if vision:
        buffer = io.BytesIO()
        colors = {
            "red": (255, 0, 0),
            "blue": (0, 0, 255),
            "green": (0, 128, 0),
            "yellow": (255, 255, 0),
            "purple": (128, 0, 128),
            "orange": (255, 165, 0),
        }
        left, right = secrets.SystemRandom().sample(list(colors), 2)
        image = Image.new("RGB", (64, 32), colors[left])
        image.paste(colors[right], (32, 0, 64, 32))
        image.save(buffer, format="PNG")
        url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        content: list[dict[str, Any]] = [
            {
                "type": "input_text" if responses else "text",
                "text": (
                    "Name the two image panel colors from left to right. "
                    "Reply with the two English color names only."
                ),
            },
            {"type": "input_image", "image_url": url}
            if responses
            else {"type": "image_url", "image_url": {"url": url}},
        ]
        body = {
            "model": model,
            "input" if responses else "messages": [
                {"role": "user", "content": content}
            ],
        }
        result = request_json(
            config, "/responses" if responses else "/chat/completions", body
        )
        text = response_text(result, responses).lower()
        if (
            left not in text
            or right not in text
            or text.index(left) >= text.index(right)
        ):
            raise ValueError("Image recognition probe failed")
        return
    function = {
        "name": "verification_echo",
        "description": (
            "Return a synthetic verification marker. This has no external effects."
        ),
        "parameters": {
            "type": "object",
            "properties": {"marker": {"type": "string"}},
            "required": ["marker"],
            "additionalProperties": False,
        },
    }
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Call verification_echo with marker {marker}, "
                "then repeat the result exactly."
            ),
        }
    ]
    body = {
        "model": model,
        "input" if responses else "messages": messages,
        "tools": [
            {"type": "function", **function}
            if responses
            else {"type": "function", "function": function}
        ],
        "tool_choice": "auto",
    }
    result = request_json(
        config, "/responses" if responses else "/chat/completions", body
    )
    if responses:
        calls = [
            i for i in result.get("output", []) if i.get("type") == "function_call"
        ]
        if len(calls) != 1:
            raise ValueError("Model did not return a tool call")
        call = calls[0]
        messages.extend(result["output"])
        messages.append(
            {
                "type": "function_call_output",
                "call_id": call["call_id"],
                "output": marker,
            }
        )
        name, arguments = call.get("name"), call.get("arguments", "{}")
    else:
        message = result.get("choices", [{}])[0].get("message", {})
        calls = message.get("tool_calls", [])
        if len(calls) != 1:
            raise ValueError("Model did not return a tool call")
        call = calls[0]
        name, arguments = (
            call.get("function", {}).get("name"),
            call.get("function", {}).get("arguments", "{}"),
        )
        messages.extend(
            [message, {"role": "tool", "tool_call_id": call["id"], "content": marker}]
        )
    if name != function["name"] or json.loads(arguments) != {"marker": marker}:
        raise ValueError("Model returned invalid tool arguments")
    body.pop("tool_choice")
    body["input" if responses else "messages"] = messages
    result = request_json(
        config, "/responses" if responses else "/chat/completions", body
    )
    text = response_text(result, responses)
    if marker not in text:
        raise ValueError("Model did not complete the tool round-trip")


def process_jobs() -> int:  # noqa: C901 - revision-bound verification transaction
    """Claim bounded verification; expired jobs fail without replaying secrets."""
    db.session.query(AiModelVerification).filter(
        AiModelVerification.status == "running",
        AiModelVerification.started_on < datetime.utcnow() - timedelta(minutes=6),
    ).update(
        {
            "status": "failed",
            "message": "Verification interrupted; retry verification",
            "candidate_json": "{}",
        }
    )
    job = (
        db.session.query(AiModelVerification)
        .filter_by(status="queued")
        .order_by(AiModelVerification.created_on)
        .with_for_update(skip_locked=True)
        .first()
    )
    if not job:
        db.session.commit()
        return 0
    job.status, job.started_on, job.message = (
        "running",
        datetime.utcnow(),
        "Discovering models and testing capabilities",
    )
    identifier = job.id
    candidate = json.loads(job.candidate_json)
    db.session.commit()
    try:
        config = candidate["config"]
        names = []
        if job.kind == "connection":
            discovered = request_json(config, "/models")
            names = [
                m["id"]
                for m in discovered.get("data", [])
                if isinstance(m, dict)
                and isinstance(m.get("id"), str)
                and 0 < len(m["id"]) <= 256
            ]
            names = list(dict.fromkeys([*names, config["llmModel"]]))
            if len(names) > 2000:
                raise ValueError("Too many discovered models")
        probe(config)
        vision = False
        try:
            probe(config, vision=True)
            vision = True
        except (ValueError, requests.RequestException, KeyError, IndexError, TypeError):
            pass
        db.session.expire_all()
        job = (
            db.session.query(AiModelVerification)
            .filter_by(id=identifier)
            .with_for_update()
            .one()
        )
        conn = (
            db.session.query(AiModelConnection)
            .filter_by(id=job.connection_id)
            .with_for_update()
            .one_or_none()
        )
        if (conn.revision if conn else 0) != job.expected_revision:
            raise ValueError("Connection changed during verification; verify again")
        if job.kind == "connection":
            if conn is None:
                conn = AiModelConnection(
                    id=job.connection_id,
                    label=candidate["label"],
                    config_json=json.dumps(config),
                    revision=1,
                )
                db.session.add(conn)
                db.session.flush()
            else:
                conn.revision += 1
                conn.label, conn.config_json = candidate["label"], json.dumps(config)
            existing = {
                m.model_name: m
                for m in db.session.query(AiModel)
                .filter_by(connection_id=conn.id)
                .all()
            }
            for m in existing.values():
                m.available = m.model_name in names
            for name in names:
                m = existing.get(name)
                if m is None:
                    m = AiModel(connection_id=conn.id, model_name=name)
                    db.session.add(m)
                m.available, m.revision, m.vision = (
                    True,
                    conn.revision,
                    vision if name == config["llmModel"] else False,
                )
                m.status = "verified" if name == config["llmModel"] else "discovered"
        else:
            model = db.session.query(AiModel).filter_by(id=job.model_id).one()
            model.revision, model.status, model.vision = (
                conn.revision,
                "verified",
                vision,
            )
        job.status, job.message = (
            "completed",
            "Chat and tool verification passed. "
            + ("Images verified." if vision else "Images are not verified."),
        )
    except (
        ValueError,
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
    ) as ex:
        db.session.rollback()
        job = db.session.query(AiModelVerification).get(identifier)
        reason = "Check the endpoint, credentials and chat/tool support."
        if isinstance(ex, requests.Timeout):
            reason = "Provider request timed out. Check network reachability."
        elif isinstance(ex, requests.ConnectionError):
            reason = "Provider connection failed. Check the endpoint and network."
        elif re.fullmatch(r"Provider returned HTTP [0-9]{3}", str(ex)):
            reason = str(ex) + ". Check credentials and provider access."
        elif str(ex) in {
            "Model did not return a tool call",
            "Model returned invalid tool arguments",
            "Model did not complete the tool round-trip",
            "Connection changed during verification; verify again",
        }:
            reason = str(ex) + "."
        job.status, job.message = (
            "failed",
            "Verification failed. "
            + reason
            + " Previous working settings were preserved.",
        )
    job.candidate_json = "{}"
    db.session.commit()
    return 1

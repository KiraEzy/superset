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
"""Destination policy and private credentials for approved MCP connections."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import secrets
import socket
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests
from flask import current_app

from superset.extensions import db
from superset.models.ai_runtime_connections import (
    AiRuntimeAccount,
    AiRuntimeConnection,
    AiRuntimeOAuthState,
)
from superset.utils import json
from superset.views.ai import config_store


class ConnectionError(ValueError):
    """A safe-to-display connection configuration or account failure."""


def validate_destination(url: str, allow_private: bool = False) -> str:
    """Reject unsafe destinations at registration and immediately before transport."""
    try:
        if not isinstance(url, str):
            raise ValueError()
        parsed = urlsplit(url)
        port = parsed.port
        if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
            raise ValueError()
        if parsed.scheme != "https" and not (allow_private and parsed.scheme == "http"):
            raise ValueError()
        addresses = socket.getaddrinfo(
            parsed.hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        if not addresses:
            raise ValueError()
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not allow_private and not ip.is_global:
                raise ValueError()
    except (ValueError, OSError) as ex:
        raise ConnectionError(
            "Destination must resolve to an approved HTTPS server"
        ) from ex
    return url


def get_connection(connection_id: str) -> AiRuntimeConnection:
    """Return an enabled approved external connection."""
    row = (
        db.session.query(AiRuntimeConnection)
        .filter_by(id=connection_id, enabled=True)
        .one_or_none()
    )
    if row is None:
        raise ConnectionError("Connection is unavailable")
    return row


def _account(connection_id: str, user_id: int, post_id: int) -> AiRuntimeAccount | None:
    return (
        db.session.query(AiRuntimeAccount)
        .filter_by(connection_id=connection_id, user_id=user_id, post_id=post_id)
        .one_or_none()
    )


def list_connections(user_id: int, post_id: int) -> list[dict[str, Any]]:
    """Expose only safe catalogue fields, never OAuth or account secrets."""
    state = config_store.resolve_active_config()
    result = []
    if state.get("mcpEnabled"):
        result.append(
            {
                "id": "focalbi",
                "label": "Focal BI",
                "linked": True,
                "auth_type": "session",
                "status": "connected",
            }
        )
    for row in db.session.query(AiRuntimeConnection).filter_by(enabled=True).all():
        linked = (
            row.auth_type == "noauth" or _account(row.id, user_id, post_id) is not None
        )
        result.append(
            {
                "id": row.id,
                "label": row.label,
                "linked": linked,
                "auth_type": row.auth_type,
                "status": "connected" if linked else "not_linked",
            }
        )
    return result


def save_connection(  # noqa: C901
    data: dict[str, Any], connection_id: str | None = None
) -> AiRuntimeConnection:
    """Persist a reviewed destination; caller enforces administrator access."""
    row = (
        db.session.query(AiRuntimeConnection).filter_by(id=connection_id).one_or_none()
        if connection_id
        else None
    )
    if connection_id and row is None:
        raise ConnectionError("Connection is unavailable")
    row = row or AiRuntimeConnection()
    auth_type = data.get("auth_type", row.auth_type)
    if auth_type not in {"token", "oauth2", "noauth"}:
        raise ConnectionError(
            "Choose token, oauth2 or explicitly reviewed noauth authentication"
        )
    allow_private = data.get("allow_private", row.allow_private or False)
    if not isinstance(allow_private, bool):
        raise ConnectionError("allow_private must be a boolean")
    label = data.get("label", row.label)
    if not isinstance(label, str) or not label.strip() or len(label) > 128:
        raise ConnectionError(
            "A connection label of at most 128 characters is required"
        )
    reviewed = data.get("reviewed_tools", json.loads(row.reviewed_tools or "{}"))
    if not isinstance(reviewed, dict) or any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or v not in {"read", "write", "destructive", "unknown"}
        for k, v in reviewed.items()
    ):
        raise ConnectionError(
            "Tool reviews must map tool names to read, write, destructive or unknown"
        )
    row.url = validate_destination(data.get("url", row.url) or "", allow_private)
    row.label, row.auth_type, row.allow_private = (
        label.strip(),
        auth_type,
        allow_private,
    )
    enabled = data.get("enabled", True if row.enabled is None else row.enabled)
    if not isinstance(enabled, bool):
        raise ConnectionError("enabled must be a boolean")
    row.enabled = enabled
    row.reviewed_tools = json.dumps(reviewed)
    if "oauth" in data:
        oauth = data["oauth"]
        if not isinstance(oauth, dict):
            raise ConnectionError("OAuth configuration must be an object")
        if not isinstance(oauth.get("scopes", []), list) or any(
            not isinstance(scope, str) for scope in oauth.get("scopes", [])
        ):
            raise ConnectionError("OAuth scopes must be a list of strings")
        for field in ("authorization_endpoint", "token_endpoint", "issuer"):
            if oauth.get(field):
                validate_destination(oauth[field], allow_private)
        row.oauth_config = json.dumps(oauth)
    # Configuration edits invalidate private grants so a changed destination can
    # never receive tokens linked against an earlier administrator review.
    if connection_id:
        db.session.query(AiRuntimeAccount).filter_by(
            connection_id=connection_id
        ).delete()
        db.session.query(AiRuntimeOAuthState).filter_by(
            connection_id=connection_id
        ).delete()
    row.version = (row.version or 0) + 1
    db.session.add(row)
    db.session.commit()
    return row


def link_token(connection_id: str, user_id: int, post_id: int, token: str) -> None:
    """Bind a token only to its authenticated owner and post."""
    row = get_connection(connection_id)
    if row.auth_type != "token" or not isinstance(token, str) or not token.strip():
        raise ConnectionError("This connection requires a nonempty personal token")
    _save_credentials(connection_id, user_id, post_id, {"access_token": token.strip()})


def _save_credentials(
    connection_id: str, user_id: int, post_id: int, credentials: dict[str, Any]
) -> None:
    account = _account(connection_id, user_id, post_id) or AiRuntimeAccount(
        connection_id=connection_id, user_id=user_id, post_id=post_id
    )
    account.credentials = json.dumps(credentials)
    db.session.add(account)
    db.session.commit()


def unlink_account(connection_id: str, user_id: int, post_id: int) -> None:
    """Remove local credentials and pending OAuth attempts without remote revocation."""
    db.session.query(AiRuntimeAccount).filter_by(
        connection_id=connection_id, user_id=user_id, post_id=post_id
    ).delete()
    db.session.query(AiRuntimeOAuthState).filter_by(
        connection_id=connection_id, user_id=user_id, post_id=post_id
    ).delete()
    db.session.commit()


def _oauth(row: AiRuntimeConnection) -> dict[str, Any]:
    config = json.loads(row.oauth_config or "{}")
    if row.auth_type != "oauth2" or any(
        not config.get(k)
        for k in (
            "authorization_endpoint",
            "token_endpoint",
            "client_id",
            "redirect_uri",
        )
    ):
        raise ConnectionError(
            "Administrator must configure OAuth endpoints, client ID and callback URI"
        )
    redirect = urlsplit(config["redirect_uri"])
    if (
        redirect.scheme != "https"
        or not redirect.netloc
        or redirect.fragment
        or redirect.username
        or redirect.password
        or redirect.query
    ):
        raise ConnectionError("OAuth requires an exact HTTPS callback URI")
    for field in ("authorization_endpoint", "token_endpoint", "issuer"):
        if config.get(field):
            validate_destination(config[field], row.allow_private)
    return config


def start_oauth(connection_id: str, user_id: int, post_id: int) -> str:
    """Create a five-minute single-use authorization attempt with PKCE S256."""
    row = get_connection(connection_id)
    config = _oauth(row)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    db.session.add(
        AiRuntimeOAuthState(
            state=state,
            connection_id=connection_id,
            user_id=user_id,
            post_id=post_id,
            verifier=verifier,
            redirect_uri=config["redirect_uri"],
            expires_on=datetime.utcnow() + timedelta(minutes=5),
        )
    )
    db.session.commit()
    return (
        config["authorization_endpoint"]
        + ("&" if "?" in config["authorization_endpoint"] else "?")
        + urlencode(
            {
                "response_type": "code",
                "client_id": config["client_id"],
                "redirect_uri": config["redirect_uri"],
                "state": state,
                "scope": " ".join(config.get("scopes", [])),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )


def finish_oauth(
    state: str,
    code: str,
    user_id: int,
    callback_uri: str,
    issuer: str | None = None,
    post_id: int | None = None,
) -> str:
    """Exchange an actor-bound state once; tokens are persisted only server-side."""
    pending = (
        db.session.query(AiRuntimeOAuthState)
        .filter_by(state=state, user_id=user_id)
        .with_for_update()
        .one_or_none()
    )
    if (
        pending is None
        or pending.expires_on <= datetime.utcnow()
        or pending.post_id != post_id
    ):
        raise ConnectionError("OAuth attempt expired or does not belong to this user")
    row = get_connection(pending.connection_id)
    config = _oauth(row)
    if not code:
        raise ConnectionError("OAuth authorization code is missing")
    if (
        callback_uri != pending.redirect_uri
        or config["redirect_uri"] != pending.redirect_uri
        or (config.get("issuer") and issuer != config["issuer"])
    ):
        raise ConnectionError(
            "OAuth callback does not match the configured redirect or issuer"
        )
    connection_id, bound_post_id, verifier = (
        pending.connection_id,
        int(pending.post_id),
        pending.verifier,
    )
    db.session.delete(pending)
    db.session.commit()
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_uri,
        "client_id": config["client_id"],
        "code_verifier": verifier,
    }
    if config.get("client_secret"):
        token_data["client_secret"] = config["client_secret"]
    credentials = _exchange(row, config, token_data)
    _save_credentials(connection_id, user_id, bound_post_id, credentials)
    return connection_id


def _exchange(
    row: AiRuntimeConnection, config: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    validate_destination(config["token_endpoint"], row.allow_private)
    try:
        response = requests.post(
            config["token_endpoint"], data=data, timeout=20, allow_redirects=False
        )
        if response.status_code != 200:
            raise ValueError()
        result = response.json()
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("access_token"), str)
            or not result["access_token"]
            or not isinstance(result.get("token_type", "Bearer"), str)
            or result.get("token_type", "Bearer").lower() != "bearer"
        ):
            raise ValueError()
        expires = result.get("expires_in")
        if expires is not None:
            result["expires_at"] = datetime.utcnow().timestamp() + float(expires)
        return result
    except (requests.RequestException, ValueError, TypeError) as ex:
        raise ConnectionError(
            "OAuth token exchange failed; reconnect your account"
        ) from ex


def validate_selection(ids: list[str], user_id: int, post_id: int) -> None:
    """Check account selection without network calls on the turn acceptance path."""
    for identifier in dict.fromkeys(ids):
        if identifier == "focalbi":
            if not config_store.resolve_active_config().get("mcpEnabled"):
                raise ConnectionError("Focal BI connection is disabled")
            continue
        row = get_connection(identifier)
        if row.auth_type != "noauth" and _account(identifier, user_id, post_id) is None:
            raise ConnectionError("Connect your account before using this server")


def resolve_connections(
    ids: list[str],
    user_id: int,
    post_id: int,
    *,
    focal_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve private credentials and revalidate approved destinations."""
    result: list[dict[str, Any]] = []
    for connection_id in dict.fromkeys(ids):
        if connection_id == "focalbi":
            config = config_store.resolve_active_config()
            from superset.views.ai.proxy import normalize_mcp_url

            if not config.get("mcpEnabled"):
                raise ConnectionError("Focal BI connection is disabled")
            if focal_config is not None:
                # A later settings edit must not redirect an accepted turn or
                # forward credentials belonging to a different destination.
                config = {
                    **config,
                    "mcpServerUrl": focal_config.get("mcpServerUrl")
                    or config["mcpServerUrl"],
                    "mcpBearerToken": focal_config.get("mcpBearerToken"),
                }
            token = (
                None
                if current_app.config.get("MCP_AUTH_ENABLED")
                else config.get("mcpBearerToken")
            )
            result.append(
                {
                    "id": "focalbi",
                    "label": "Focal BI",
                    "url": normalize_mcp_url(config["mcpServerUrl"]),
                    "bearer_token": token,
                    "is_focal": True,
                    "reviewed_tools": {},
                    "allow_private": True,
                    "version": 1,
                }
            )
            continue
        row = get_connection(connection_id)
        validate_destination(row.url, row.allow_private)
        account = _account(connection_id, user_id, post_id)
        credentials = json.loads(account.credentials) if account else {}
        if row.auth_type != "noauth" and not credentials.get("access_token"):
            raise ConnectionError("Connect your account before using this server")
        if credentials.get("expires_at", float("inf")) <= datetime.utcnow().timestamp():
            if not credentials.get("refresh_token"):
                raise ConnectionError("Account expired; reconnect your account")
            config = _oauth(row)
            data = {
                "grant_type": "refresh_token",
                "refresh_token": credentials["refresh_token"],
                "client_id": config["client_id"],
            }
            if config.get("client_secret"):
                data["client_secret"] = config["client_secret"]
            renewed = _exchange(row, config, data)
            credentials.update(renewed)
            _save_credentials(connection_id, user_id, post_id, credentials)
        result.append(
            {
                "id": row.id,
                "label": row.label,
                "url": row.url,
                "bearer_token": credentials.get("access_token"),
                "is_focal": False,
                "reviewed_tools": json.loads(row.reviewed_tools or "{}"),
                "allow_private": row.allow_private,
                "version": row.version,
            }
        )
    return result

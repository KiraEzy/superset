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
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from flask import current_app, g
from flask_appbuilder.security.sqla.models import User


class McpJwtError(ValueError):
    """Raised when a post-scoped MCP JWT cannot be minted."""


def _jwt_secret() -> str:
    secret = current_app.config.get("MCP_JWT_SECRET")
    if not secret:
        raise McpJwtError("MCP_JWT_SECRET is not configured")
    return str(secret)


def _jwt_algorithm() -> str:
    return str(current_app.config.get("MCP_JWT_ALGORITHM") or "HS256")


def _jwt_issuer() -> str | None:
    return current_app.config.get("MCP_JWT_ISSUER")


def _jwt_audience() -> str | None:
    return current_app.config.get("MCP_JWT_AUDIENCE")


def _jwt_ttl_seconds() -> int:
    from superset.global_configuration import store as global_config_store
    from superset.global_configuration.registry import KEY_MCP_JWT_TTL_SECONDS

    known = global_config_store.effective_known_map()
    return int(known.get(KEY_MCP_JWT_TTL_SECONDS, 600))


def mint_mcp_user_token(*, user: User, active_post_id: int | None) -> str:
    if not active_post_id:
        raise McpJwtError("Select an active post before using Focal AI MCP tools")

    # Validate the explicit post id against the user's assigned posts
    # (same ownership query as set_active_post), not session state.
    from superset import security_manager

    posts = {p.id for p in security_manager.get_user_posts(user)}
    if active_post_id not in posts:
        raise McpJwtError("Active post is not assigned to the current user")

    now = datetime.now(timezone.utc)
    ttl = _jwt_ttl_seconds()
    payload: dict[str, Any] = {
        "sub": user.username,
        "username": user.username,
        "active_post_id": int(active_post_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    issuer = _jwt_issuer()
    audience = _jwt_audience()
    if issuer:
        payload["iss"] = issuer
    if audience:
        payload["aud"] = audience

    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def resolve_chat_mcp_bearer_token() -> str:
    """Mint a post-scoped token for the current request user."""
    from superset import security_manager

    user = g.user
    active_post_id = security_manager.get_active_post_id()
    return mint_mcp_user_token(user=user, active_post_id=active_post_id)

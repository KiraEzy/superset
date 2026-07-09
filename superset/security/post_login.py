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
"""Post-login gate enforcing active-post selection (ADR-5).

For an authenticated web user with no active post:
- 0 posts  -> allowed through (they simply have no permissions); the frontend
  shows an "ask an admin" state.
- 1 post   -> auto-selected transparently (also done at login via signal).
- 2+ posts -> HTML page navigations are redirected to the post picker. API/XHR
  requests are left alone (they return post-scoped, i.e. empty, permissions
  until a post is chosen), so no redirect loops occur.

A stale ``active_post_id`` left in the session from a previous user is cleared
and re-evaluated so it cannot block auto-select or leave the user with zero
roles.
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import current_app, g, redirect, request, Response

logger = logging.getLogger(__name__)

CHOOSE_POST_PATH = "/superset/choose-post/"

# Path prefixes that must never be redirected to the picker to avoid loops and
# to keep auth/static/health/the picker itself reachable.
_EXEMPT_PREFIXES = (
    "/superset/choose-post",
    "/login",
    "/logout",
    "/register",
    "/api/",
    "/static/",
    "/health",
    "/healthcheck",
    "/ping",
    "/superset/log",
    "/resetmypassword",
)


def _is_exempt_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _wants_html() -> bool:
    best = request.accept_mimetypes.best_match(["text/html", "application/json"])
    return (
        best == "text/html"
        and request.accept_mimetypes[best] > request.accept_mimetypes["application/json"]
    )


def post_login_gate() -> Optional[Response]:
    """Flask ``before_request`` handler. Returns a redirect Response or None."""
    if not current_app.config.get("FOCAL_POST_RBAC_ENABLED", True):
        return None

    if request.method != "GET":
        return None

    from superset import security_manager

    if not hasattr(security_manager, "get_user_posts"):
        return None

    user = g.user if hasattr(g, "user") else None
    if user is None or user.is_anonymous:
        return None
    if security_manager.is_guest_user(user):
        return None

    # Fix 2: clear stale active_post_id and auto-select a single post when needed.
    # Login already does this via the user_logged_in signal; the gate covers
    # sessions that skipped that path (e.g. restored cookies, older code).
    security_manager.maybe_auto_select_single_post(user)

    if security_manager.is_active_post_assigned(user):
        return None

    posts = security_manager.get_user_posts(user)

    # Single post should already have been selected above.
    if len(posts) <= 1:
        return None

    # 2+ posts: redirect only real page navigations to the picker.
    if _is_exempt_path(request.path):
        return None
    if not _wants_html():
        return None

    return redirect(CHOOSE_POST_PATH)

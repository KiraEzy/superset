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
"""Custom security manager implementing User -> Post -> Role -> Permission RBAC.

For a logged-in web user, the roles that grant permissions come ONLY from the
single active Post selected at login (stored in the Flask session). Direct
``ab_user_role`` rows and FAB group roles are ignored for authorization.

Non-web / system contexts (CLI, migrations, Celery tasks, MCP) have no browser
session, so they fall back to the union of every role granted by all of the
user's posts, keeping background processing unrestricted (ADR-3).

Anonymous and guest-token users keep their existing behavior unchanged.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from flask import Flask, current_app, g, has_request_context, session
from flask_appbuilder.security.sqla.models import (
    assoc_permissionview_role,
    Role,
    User,
)
from flask_login import LoginManager, user_logged_in, user_logged_out
from sqlalchemy import and_, update

from superset.security.manager import SupersetSecurityManager

logger = logging.getLogger(__name__)

ACTIVE_POST_SESSION_KEY = "active_post_id"
ACTIVE_POST_NAME_SESSION_KEY = "active_post_name"


def _post_models():
    """Import Post models lazily to avoid circular imports during config load."""
    from superset.models.post import assoc_post_role, assoc_user_post, Post

    return Post, assoc_post_role, assoc_user_post


class PostAccessError(Exception):
    """Raised when a user tries to activate a post they are not assigned to."""


class FocalSecurityManager(SupersetSecurityManager):
    """Security manager that scopes role resolution to the active post."""

    # ------------------------------------------------------------------
    # Feature toggle
    # ------------------------------------------------------------------
    @staticmethod
    def _post_rbac_enabled() -> bool:
        return bool(current_app.config.get("FOCAL_POST_RBAC_ENABLED", True))

    # ------------------------------------------------------------------
    # Post helpers
    # ------------------------------------------------------------------
    def get_user_posts(self, user: Optional[User] = None) -> list:
        """Return the active posts assigned to ``user`` ordered by last used."""
        Post, _, assoc_user_post = _post_models()
        if user is None:
            user = g.user if (has_request_context() and hasattr(g, "user")) else None
        if user is None or user.is_anonymous:
            return []
        return (
            self.session.query(Post)
            .join(assoc_user_post, assoc_user_post.c.post_id == Post.id)
            .filter(assoc_user_post.c.user_id == user.id)
            .filter(Post.active.is_(True))
            .order_by(assoc_user_post.c.last_used_on.desc().nullslast())
            .all()
        )

    def get_active_post_id(self) -> Optional[int]:
        if has_request_context() and getattr(g, "mcp_active_post_id", None):
            return int(g.mcp_active_post_id)
        if not has_request_context():
            return None
        return session.get(ACTIVE_POST_SESSION_KEY)

    def get_last_used_post_id(self, user: User) -> Optional[int]:
        Post, _, assoc_user_post = _post_models()
        row = (
            self.session.query(assoc_user_post.c.post_id)
            .join(Post, Post.id == assoc_user_post.c.post_id)
            .filter(assoc_user_post.c.user_id == user.id)
            .filter(Post.active.is_(True))
            .filter(assoc_user_post.c.last_used_on.isnot(None))
            .order_by(assoc_user_post.c.last_used_on.desc())
            .first()
        )
        return row[0] if row else None

    def set_active_post(self, user: User, post_id: int):
        """Validate that ``post_id`` belongs to ``user`` and activate it."""
        Post, _, assoc_user_post = _post_models()
        post = (
            self.session.query(Post)
            .join(assoc_user_post, assoc_user_post.c.post_id == Post.id)
            .filter(assoc_user_post.c.user_id == user.id)
            .filter(Post.id == post_id)
            .filter(Post.active.is_(True))
            .one_or_none()
        )
        if post is None:
            raise PostAccessError(
                f"Post {post_id} is not assigned to user {user.username}"
            )
        session[ACTIVE_POST_SESSION_KEY] = post.id
        session[ACTIVE_POST_NAME_SESSION_KEY] = post.name
        self.session.execute(
            update(assoc_user_post)
            .where(
                and_(
                    assoc_user_post.c.user_id == user.id,
                    assoc_user_post.c.post_id == post.id,
                )
            )
            .values(last_used_on=datetime.utcnow())
        )
        self.session.commit()
        return post

    def clear_active_post(self) -> None:
        if has_request_context():
            session.pop(ACTIVE_POST_SESSION_KEY, None)
            session.pop(ACTIVE_POST_NAME_SESSION_KEY, None)

    def is_active_post_assigned(self, user: User) -> bool:
        """Return True when session ``active_post_id`` belongs to ``user``."""
        active_id = self.get_active_post_id()
        if not active_id:
            return False
        return any(post.id == active_id for post in self.get_user_posts(user))

    def maybe_auto_select_single_post(self, user: Optional[User]) -> None:
        """Clear a stale active post and auto-select when the user has exactly one.

        Called on login and from the request gate so single-post users get
        permissions immediately, and a leftover ``active_post_id`` from a
        previous session cannot block re-selection.
        """
        if not self._post_rbac_enabled():
            return
        if user is None or getattr(user, "is_anonymous", True):
            return
        if self.is_guest_user(user):
            return
        if not has_request_context():
            return

        posts = self.get_user_posts(user)
        post_ids = {post.id for post in posts}
        active_id = self.get_active_post_id()

        # Stale session from a previous user (or revoked assignment).
        if active_id and active_id not in post_ids:
            self.clear_active_post()
            active_id = None

        if active_id:
            return

        if len(posts) != 1:
            return

        try:
            self.set_active_post(user, posts[0].id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to auto-select single post for user %s",
                getattr(user, "username", user),
                exc_info=True,
            )

    def create_login_manager(self, app: Flask) -> LoginManager:
        """Wire login/logout signals so active-post session stays in sync."""
        lm = super().create_login_manager(app)

        # Keep strong refs on the instance. Nested functions with blinker's
        # default weak=True are GC'd as soon as this method returns.
        # Connect with sender=ANY: create_login_manager may run against an app
        # identity that does not match current_app at login/logout time.
        if getattr(self, "_on_user_logged_out", None) is not None:
            user_logged_out.disconnect(self._on_user_logged_out)
        if getattr(self, "_on_user_logged_in", None) is not None:
            user_logged_in.disconnect(self._on_user_logged_in)

        self._on_user_logged_out = self._handle_user_logged_out
        self._on_user_logged_in = self._handle_user_logged_in
        user_logged_out.connect(self._on_user_logged_out, weak=False)
        user_logged_in.connect(self._on_user_logged_in, weak=False)

        return lm

    def _handle_user_logged_out(self, sender, user=None, **kwargs) -> None:  # noqa: ARG002
        # Fix 1: drop active_post_id so the next login cannot inherit it.
        if self._post_rbac_enabled():
            self.clear_active_post()

    def _handle_user_logged_in(self, sender, user=None, **kwargs) -> None:  # noqa: ARG002
        # Fix 3: set active_post_id during login for single-post users.
        self.maybe_auto_select_single_post(user)

    # ------------------------------------------------------------------
    # Role resolution helpers
    # ------------------------------------------------------------------
    def _roles_for_active_post(self, user: User, post_id: int) -> list[Role]:
        _, assoc_post_role, assoc_user_post = _post_models()
        return (
            self.session.query(Role)
            .join(assoc_post_role, assoc_post_role.c.role_id == Role.id)
            .join(
                assoc_user_post,
                and_(
                    assoc_user_post.c.post_id == assoc_post_role.c.post_id,
                    assoc_user_post.c.user_id == user.id,
                ),
            )
            .filter(assoc_post_role.c.post_id == post_id)
            .all()
        )

    def _all_post_roles(self, user: User) -> list[Role]:
        _, assoc_post_role, assoc_user_post = _post_models()
        return (
            self.session.query(Role)
            .join(assoc_post_role, assoc_post_role.c.role_id == Role.id)
            .join(
                assoc_user_post,
                assoc_user_post.c.post_id == assoc_post_role.c.post_id,
            )
            .filter(assoc_user_post.c.user_id == user.id)
            .distinct()
            .all()
        )

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------
    def get_user_roles(self, user: Optional[User] = None) -> list[Role]:
        if not self._post_rbac_enabled():
            return super().get_user_roles(user)

        if user is None:
            user = g.user if (has_request_context() and hasattr(g, "user")) else None

        # Userless system context (e.g. Celery with no user): nothing to scope.
        if user is None:
            return []

        # Anonymous users keep the public-role behavior from the base manager.
        if user.is_anonymous:
            return super().get_user_roles(user)

        # Guest-token (embedded) users carry their roles on the token object.
        if self.is_guest_user(user):
            return super().get_user_roles(user)

        # System / no-session context: union of every post's roles (unscoped).
        if not has_request_context():
            return self._all_post_roles(user)

        # Logged-in web user: only the active post's roles grant permissions.
        active_post_id = self.get_active_post_id()
        if not active_post_id:
            return []
        return self._roles_for_active_post(user, active_post_id)

    def get_user_roles_permissions(
        self, user: Optional[User] = None
    ) -> dict[str, list[list[str]]]:
        """Build the role -> permissions map from the post-scoped roles.

        The FAB base implementation reads ``user.roles`` directly, which would
        ignore post scoping. We rebuild it from :meth:`get_user_roles` so the
        bootstrap payload (and therefore frontend permission checks) reflect the
        active post only.
        """
        if not self._post_rbac_enabled():
            return super().get_user_roles_permissions(user)

        if user is None:
            user = g.user if (has_request_context() and hasattr(g, "user")) else None
        if user is None or user.is_anonymous:
            return super().get_user_roles_permissions(user)
        if self.is_guest_user(user):
            return super().get_user_roles_permissions(user)

        result: dict[str, list[list[str]]] = {}
        for role in self.get_user_roles(user):
            perms: list[list[str]] = []
            for pvm in role.permissions:
                if pvm.permission and pvm.view_menu:
                    perms.append([pvm.permission.name, pvm.view_menu.name])
            result[role.name] = perms
        return result

    def user_view_menu_names(self, permission_name: str) -> set[str]:
        if not self._post_rbac_enabled():
            return super().user_view_menu_names(permission_name)

        base_query = (
            self.session.query(self.viewmenu_model.name)
            .join(self.permissionview_model)
            .join(self.permission_model)
            .join(assoc_permissionview_role)
            .join(self.role_model)
        )

        role_ids = [role.id for role in self.get_user_roles()]
        if not role_ids:
            return set()

        view_menu_names = (
            base_query.filter(self.role_model.id.in_(role_ids)).filter(
                self.permission_model.name == permission_name
            )
        ).all()
        return {s.name for s in view_menu_names}

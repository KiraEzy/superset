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
"""REST APIs for Post administration and active-post selection.

- ``PostRestApi`` (``/api/v1/post``): admin CRUD for posts plus role/user
  assignment. Gated by the ``Post`` permission (Admin only in practice).
- ``ActivePostRestApi`` (``/api/v1/active_post``): lets the current user read
  the posts available to them and choose which one to act as for the session.
  Intentionally NOT permission-gated: right after login a user has no active
  post (hence no roles), so a permission check would make it impossible to ever
  select a post. Authentication is still required.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import g, request, Response
from flask_appbuilder.api import expose, protect, safe
from flask_appbuilder.security.sqla.models import Role, User

from superset import security_manager
from superset.extensions import db, event_logger
from superset.models.post import Post
from superset.security.focal_manager import PostAccessError
from superset.views.base_api import BaseSupersetApi, statsd_metrics

logger = logging.getLogger(__name__)


def _post_to_dict(post: Post) -> dict[str, Any]:
    return {
        "id": post.id,
        "name": post.name,
        "label": post.label,
        "description": post.description,
        "active": post.active,
        "role_ids": [role.id for role in post.roles],
        "role_names": [role.name for role in post.roles],
        "user_ids": [user.id for user in post.users],
        "users": [
            {"id": user.id, "username": user.username} for user in post.users
        ],
        "user_count": len(post.users),
    }


class PostRestApi(BaseSupersetApi):
    """Admin CRUD for posts and post<->role / post<->user assignment."""

    resource_name = "post"
    allow_browser_login = True
    class_permission_name = "Post"
    openapi_spec_tag = "Post"
    method_permission_name = {
        "get_list": "read",
        "get_item": "read",
        "post": "write",
        "put": "write",
        "delete": "write",
        "set_roles": "write",
        "set_users": "write",
        "set_user_posts": "write",
    }

    def _require_admin(self) -> Response | None:
        if not security_manager.is_admin():
            return self.response_403()
        return None

    @expose("/", methods=("GET",))
    @protect()
    @safe
    @statsd_metrics
    def get_list(self) -> Response:
        """List all posts with their role and user ids."""
        posts = db.session.query(Post).order_by(Post.name).all()
        return self.response(
            200,
            result=[_post_to_dict(p) for p in posts],
            count=len(posts),
        )

    @expose("/<int:pk>", methods=("GET",))
    @protect()
    @safe
    @statsd_metrics
    def get_item(self, pk: int) -> Response:
        """Get a single post."""
        post = db.session.query(Post).filter(Post.id == pk).one_or_none()
        if post is None:
            return self.response_404()
        return self.response(200, result=_post_to_dict(post))

    @expose("/", methods=("POST",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this
    def post(self) -> Response:
        """Create a post."""
        if (denied := self._require_admin()) is not None:
            return denied
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return self.response_400(message="Post name is required")
        if db.session.query(Post).filter(Post.name == name).first():
            return self.response_422(message="A post with this name already exists")

        post = Post(
            name=name,
            label=data.get("label"),
            description=data.get("description"),
            active=data.get("active", True),
        )
        self._apply_roles(post, data.get("role_ids"))
        self._apply_users(post, data.get("user_ids"))
        db.session.add(post)
        db.session.commit()
        return self.response(201, id=post.id, result=_post_to_dict(post))

    @expose("/<int:pk>", methods=("PUT",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this
    def put(self, pk: int) -> Response:
        """Update a post."""
        if (denied := self._require_admin()) is not None:
            return denied
        post = db.session.query(Post).filter(Post.id == pk).one_or_none()
        if post is None:
            return self.response_404()
        data = request.get_json(silent=True) or {}
        if "name" in data:
            new_name = (data.get("name") or "").strip()
            if not new_name:
                return self.response_400(message="Post name is required")
            existing = (
                db.session.query(Post)
                .filter(Post.name == new_name, Post.id != pk)
                .first()
            )
            if existing:
                return self.response_422(
                    message="A post with this name already exists"
                )
            post.name = new_name
        if "label" in data:
            post.label = data.get("label")
        if "description" in data:
            post.description = data.get("description")
        if "active" in data:
            post.active = bool(data.get("active"))
        if "role_ids" in data:
            self._apply_roles(post, data.get("role_ids"))
        if "user_ids" in data:
            self._apply_users(post, data.get("user_ids"))
        db.session.commit()
        return self.response(200, result=_post_to_dict(post))

    @expose("/<int:pk>", methods=("DELETE",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this
    def delete(self, pk: int) -> Response:
        """Delete a post."""
        if (denied := self._require_admin()) is not None:
            return denied
        post = db.session.query(Post).filter(Post.id == pk).one_or_none()
        if post is None:
            return self.response_404()
        post.roles = []
        post.users = []
        db.session.delete(post)
        db.session.commit()
        return self.response(200, message="OK")

    @expose("/<int:pk>/roles", methods=("PUT",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this
    def set_roles(self, pk: int) -> Response:
        """Replace the roles granted by a post."""
        if (denied := self._require_admin()) is not None:
            return denied
        post = db.session.query(Post).filter(Post.id == pk).one_or_none()
        if post is None:
            return self.response_404()
        data = request.get_json(silent=True) or {}
        self._apply_roles(post, data.get("role_ids", []))
        db.session.commit()
        return self.response(200, result=_post_to_dict(post))

    @expose("/<int:pk>/users", methods=("PUT",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this
    def set_users(self, pk: int) -> Response:
        """Replace the users assigned to a post."""
        if (denied := self._require_admin()) is not None:
            return denied
        post = db.session.query(Post).filter(Post.id == pk).one_or_none()
        if post is None:
            return self.response_404()
        data = request.get_json(silent=True) or {}
        self._apply_users(post, data.get("user_ids", []))
        db.session.commit()
        return self.response(200, result=_post_to_dict(post))

    @expose("/user/<int:user_id>", methods=("PUT",))
    @protect()
    @safe
    @statsd_metrics
    @event_logger.log_this
    def set_user_posts(self, user_id: int) -> Response:
        """Replace the posts a given user is assigned to."""
        if (denied := self._require_admin()) is not None:
            return denied
        user = db.session.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            return self.response_404()
        data = request.get_json(silent=True) or {}
        post_ids = data.get("post_ids", []) or []
        posts = db.session.query(Post).filter(Post.id.in_(post_ids)).all()
        user.posts = posts
        db.session.commit()
        return self.response(
            200,
            result={"user_id": user.id, "post_ids": [p.id for p in posts]},
        )

    @staticmethod
    def _apply_roles(post: Post, role_ids: list[int] | None) -> None:
        if role_ids is None:
            return
        post.roles = db.session.query(Role).filter(Role.id.in_(role_ids)).all()

    @staticmethod
    def _apply_users(post: Post, user_ids: list[int] | None) -> None:
        if user_ids is None:
            return
        post.users = db.session.query(User).filter(User.id.in_(user_ids)).all()


class ActivePostRestApi(BaseSupersetApi):
    """Read/select the active post for the current session (auth-only)."""

    resource_name = "active_post"
    allow_browser_login = True
    openapi_spec_tag = "Post"

    @staticmethod
    def _serialize(post: Post) -> dict[str, Any]:
        return {"id": post.id, "name": post.name, "label": post.label}

    @expose("/", methods=("GET",))
    @safe
    @statsd_metrics
    def get_active(self) -> Response:
        """Return the current active post and the posts available to the user."""
        if not g.user or g.user.is_anonymous:
            return self.response_401()
        available = security_manager.get_user_posts(g.user)
        active_id = security_manager.get_active_post_id()
        active = next((p for p in available if p.id == active_id), None)
        return self.response(
            200,
            result={
                "active_post": self._serialize(active) if active else None,
                "available_posts": [self._serialize(p) for p in available],
            },
        )

    @expose("/", methods=("POST",))
    @safe
    @statsd_metrics
    @event_logger.log_this
    def set_active(self) -> Response:
        """Set the active post for the current session."""
        if not g.user or g.user.is_anonymous:
            return self.response_401()
        data = request.get_json(silent=True) or {}
        post_id = data.get("post_id")
        if post_id is None:
            return self.response_400(message="post_id is required")
        try:
            post = security_manager.set_active_post(g.user, int(post_id))
        except PostAccessError as ex:
            return self.response_403(message=str(ex))
        return self.response(200, result=self._serialize(post))

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
"""Integration tests for post-based RBAC scoping.

These tests exercise the ``FocalSecurityManager`` active-post scoping. They are
skipped automatically when the configured security manager does not implement
the post helpers (i.e. ``FOCAL_POST_RBAC_ENABLED`` / ``CUSTOM_SECURITY_MANAGER``
is not wired to ``FocalSecurityManager``).
"""

import pytest
from flask import current_app, g

from superset import db, security_manager
from superset.models.post import Post

pytestmark = pytest.mark.skipif(
    not hasattr(security_manager, "set_active_post"),
    reason="FocalSecurityManager (post-based RBAC) is not active",
)


def _make_role(name, permissions):
    pvms = [security_manager.add_permission_view_menu(p, v) for p, v in permissions]
    return security_manager.add_role(name, pvms)


@pytest.fixture
def user_with_two_posts(app_context):
    finance_role = _make_role(
        "post_finance", [("menu_access", "PostFinanceMenu")]
    )
    hr_role = _make_role("post_hr", [("menu_access", "PostHrMenu")])

    finance_post = Post(name="Finance Analyst", active=True, roles=[finance_role])
    hr_post = Post(name="HR Analyst", active=True, roles=[hr_role])
    db.session.add_all([finance_post, hr_post])
    db.session.flush()

    user = security_manager.add_user(
        "post_multi_user",
        "post",
        "multi",
        "post_multi_user@example.com",
        role=[],
    )
    user.posts = [finance_post, hr_post]
    db.session.commit()

    yield {
        "user": user,
        "finance_post": finance_post,
        "hr_post": hr_post,
        "finance_role": finance_role,
        "hr_role": hr_role,
    }

    db.session.delete(user)
    db.session.delete(finance_post)
    db.session.delete(hr_post)
    db.session.delete(finance_role)
    db.session.delete(hr_role)
    db.session.commit()


def test_get_user_roles_scopes_to_active_post(user_with_two_posts):
    ctx = user_with_two_posts
    user = ctx["user"]
    with current_app.test_request_context():
        g.user = user
        security_manager.set_active_post(user, ctx["finance_post"].id)
        role_names = {role.name for role in security_manager.get_user_roles(user)}
        assert role_names == {"post_finance"}

        security_manager.set_active_post(user, ctx["hr_post"].id)
        role_names = {role.name for role in security_manager.get_user_roles(user)}
        assert role_names == {"post_hr"}


def test_no_active_post_returns_no_roles(user_with_two_posts):
    user = user_with_two_posts["user"]
    with current_app.test_request_context():
        g.user = user
        assert security_manager.get_user_roles(user) == []


def test_system_context_returns_union_of_post_roles(user_with_two_posts):
    # No request context -> system/full resolution: union of all post roles.
    user = user_with_two_posts["user"]
    role_names = {role.name for role in security_manager.get_user_roles(user)}
    assert role_names == {"post_finance", "post_hr"}


def test_set_active_post_rejects_unassigned_post(user_with_two_posts):
    from superset.security.focal_manager import PostAccessError

    user = user_with_two_posts["user"]
    orphan = Post(name="Orphan Post", active=True)
    db.session.add(orphan)
    db.session.commit()
    try:
        with current_app.test_request_context():
            g.user = user
            with pytest.raises(PostAccessError):
                security_manager.set_active_post(user, orphan.id)
    finally:
        db.session.delete(orphan)
        db.session.commit()


@pytest.fixture
def user_with_one_post(app_context):
    viewer_role = _make_role(
        "post_viewer_single", [("menu_access", "PostViewerMenu")]
    )
    viewer_post = Post(name="Viewer Post", active=True, roles=[viewer_role])
    db.session.add(viewer_post)
    db.session.flush()

    user = security_manager.add_user(
        "post_single_user",
        "post",
        "single",
        "post_single_user@example.com",
        role=[],
    )
    user.posts = [viewer_post]
    db.session.commit()

    yield {
        "user": user,
        "post": viewer_post,
        "role": viewer_role,
    }

    db.session.delete(user)
    db.session.delete(viewer_post)
    db.session.delete(viewer_role)
    db.session.commit()


def test_clear_active_post_removes_session_keys(user_with_one_post):
    """Fix 1: clear_active_post drops session keys used for post scoping."""
    from flask import session

    from superset.security.focal_manager import (
        ACTIVE_POST_NAME_SESSION_KEY,
        ACTIVE_POST_SESSION_KEY,
    )

    ctx = user_with_one_post
    with current_app.test_request_context():
        g.user = ctx["user"]
        security_manager.set_active_post(ctx["user"], ctx["post"].id)
        assert session.get(ACTIVE_POST_SESSION_KEY) == ctx["post"].id
        assert session.get(ACTIVE_POST_NAME_SESSION_KEY) == ctx["post"].name

        security_manager.clear_active_post()
        assert ACTIVE_POST_SESSION_KEY not in session
        assert ACTIVE_POST_NAME_SESSION_KEY not in session


def test_stale_active_post_is_cleared_and_single_post_auto_selected(
    user_with_one_post, user_with_two_posts
):
    """Fix 2: a leftover active_post_id from another user is cleared and replaced."""
    from flask import session

    from superset.security.focal_manager import ACTIVE_POST_SESSION_KEY

    single = user_with_one_post
    other_post_id = user_with_two_posts["finance_post"].id

    with current_app.test_request_context():
        g.user = single["user"]
        # Simulate stale session left by a previous login.
        session[ACTIVE_POST_SESSION_KEY] = other_post_id
        assert not security_manager.is_active_post_assigned(single["user"])

        security_manager.maybe_auto_select_single_post(single["user"])

        assert security_manager.get_active_post_id() == single["post"].id
        assert security_manager.is_active_post_assigned(single["user"])
        role_names = {role.name for role in security_manager.get_user_roles(single["user"])}
        assert role_names == {"post_viewer_single"}


def test_login_auto_selects_single_post(user_with_one_post):
    """Fix 3: user_logged_in path auto-selects when the user has exactly one post."""
    ctx = user_with_one_post
    with current_app.test_request_context():
        g.user = ctx["user"]
        assert security_manager.get_active_post_id() is None

        security_manager.maybe_auto_select_single_post(ctx["user"])

        assert security_manager.get_active_post_id() == ctx["post"].id
        role_names = {role.name for role in security_manager.get_user_roles(ctx["user"])}
        assert role_names == {"post_viewer_single"}


def test_login_does_not_auto_select_for_multi_post_user(user_with_two_posts):
    """Multi-post users must pick explicitly; login must not invent an active post."""
    user = user_with_two_posts["user"]
    with current_app.test_request_context():
        g.user = user
        security_manager.maybe_auto_select_single_post(user)
        assert security_manager.get_active_post_id() is None
        assert security_manager.get_user_roles(user) == []


def test_post_login_gate_redirects_multi_post_html(user_with_two_posts):
    from superset.security.post_login import CHOOSE_POST_PATH, post_login_gate

    user = user_with_two_posts["user"]
    with current_app.test_request_context(
        "/superset/welcome/",
        method="GET",
        headers={"Accept": "text/html"},
    ):
        g.user = user
        response = post_login_gate()
        assert response is not None
        assert response.status_code in (302, 301)
        assert CHOOSE_POST_PATH in response.location


def test_post_login_gate_clears_stale_and_skips_redirect_for_single_post(
    user_with_one_post, user_with_two_posts
):
    from flask import session

    from superset.security.focal_manager import ACTIVE_POST_SESSION_KEY
    from superset.security.post_login import post_login_gate

    single = user_with_one_post
    with current_app.test_request_context(
        "/api/v1/dashboard/",
        method="GET",
        headers={"Accept": "application/json"},
    ):
        g.user = single["user"]
        session[ACTIVE_POST_SESSION_KEY] = user_with_two_posts["finance_post"].id

        assert post_login_gate() is None
        assert security_manager.get_active_post_id() == single["post"].id

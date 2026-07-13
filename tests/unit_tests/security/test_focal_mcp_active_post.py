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
"""Unit tests for MCP request-scoped active post override."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from flask import Flask, g, session


def _make_manager():
    from superset.security.focal_manager import FocalSecurityManager

    return FocalSecurityManager.__new__(FocalSecurityManager)


def test_get_active_post_id_prefers_mcp_override():
    from superset.security.focal_manager import ACTIVE_POST_SESSION_KEY

    app = Flask(__name__)
    app.secret_key = "test"
    mgr = _make_manager()

    with app.test_request_context("/"):
        session[ACTIVE_POST_SESSION_KEY] = 1
        g.mcp_active_post_id = 42
        assert mgr.get_active_post_id() == 42


def test_get_active_post_id_falls_back_to_session():
    from superset.security.focal_manager import ACTIVE_POST_SESSION_KEY

    app = Flask(__name__)
    app.secret_key = "test"
    mgr = _make_manager()

    with app.test_request_context("/"):
        session[ACTIVE_POST_SESSION_KEY] = 7
        assert not hasattr(g, "mcp_active_post_id")
        assert mgr.get_active_post_id() == 7


def test_get_user_roles_uses_g_user_without_request_context():
    """Dataset access filters call get_user_roles() with no user arg under MCP."""
    app = Flask(__name__)
    mgr = _make_manager()

    user = MagicMock()
    user.is_anonymous = False
    expected_role = MagicMock()
    expected_role.name = "Explorer"

    with app.app_context():
        g.user = user
        g.mcp_active_post_id = 3
        with (
            patch.object(mgr, "_post_rbac_enabled", return_value=True),
            patch.object(mgr, "is_guest_user", return_value=False),
            patch.object(
                mgr, "_roles_for_active_post", return_value=[expected_role]
            ) as mock_roles,
        ):
            result = mgr.get_user_roles()  # no explicit user

        mock_roles.assert_called_once_with(user, 3)
        assert result == [expected_role]


def test_get_active_post_id_mcp_override_without_request_context():
    """MCP Starlette requests often have app context only — still honor g bind."""
    app = Flask(__name__)
    mgr = _make_manager()

    with app.app_context():
        g.mcp_active_post_id = 99
        assert mgr.get_active_post_id() == 99


def test_get_user_roles_uses_mcp_post_without_request_context():
    """tools/list filtering must not fall back to all-post roles when JWT binds."""
    app = Flask(__name__)
    mgr = _make_manager()

    user = MagicMock()
    user.is_anonymous = False
    expected_role = MagicMock()
    expected_role.name = "ViewerOnly"

    with app.app_context():
        g.mcp_active_post_id = 4
        with (
            patch.object(mgr, "_post_rbac_enabled", return_value=True),
            patch.object(mgr, "is_guest_user", return_value=False),
            patch.object(
                mgr, "_roles_for_active_post", return_value=[expected_role]
            ) as mock_roles,
            patch.object(mgr, "_all_post_roles") as mock_all,
        ):
            result = mgr.get_user_roles(user)

        mock_roles.assert_called_once_with(user, 4)
        mock_all.assert_not_called()
        assert result == [expected_role]


def test_get_user_roles_uses_mcp_post():
    """get_user_roles must resolve roles via get_active_post_id MCP override."""
    from superset.security.focal_manager import ACTIVE_POST_SESSION_KEY

    app = Flask(__name__)
    app.secret_key = "test"
    mgr = _make_manager()

    user = MagicMock()
    user.is_anonymous = False
    expected_role = MagicMock()
    expected_role.name = "Post42Role"

    with app.test_request_context("/"):
        session[ACTIVE_POST_SESSION_KEY] = 1
        g.mcp_active_post_id = 42
        with (
            patch.object(mgr, "_post_rbac_enabled", return_value=True),
            patch.object(mgr, "is_guest_user", return_value=False),
            patch.object(
                mgr, "_roles_for_active_post", return_value=[expected_role]
            ) as mock_roles,
        ):
            result = mgr.get_user_roles(user)

        mock_roles.assert_called_once_with(user, 42)
        assert result == [expected_role]

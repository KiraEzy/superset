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
"""Unit tests for post-scoped MCP JWT user resolution in auth.py.

Loads ``auth.py`` by file path so collection does not execute
``superset`` package init (requires a fully initialized app / babel).
Uses a lightweight Flask app + mocks (Docker may lack full conftest).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

_MODULE_NAME = "superset.mcp_service.auth"


def _ensure_package(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = ModuleType(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = mod
    parent, _, attr = name.rpartition(".")
    if parent:
        setattr(sys.modules[parent], attr, mod)
    return mod


def _load_auth() -> ModuleType:
    if _MODULE_NAME in sys.modules and hasattr(
        sys.modules[_MODULE_NAME], "get_user_from_request"
    ):
        return sys.modules[_MODULE_NAME]

    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "superset" / "mcp_service" / "auth.py"
    if not path.is_file():
        path = Path("/app/superset/mcp_service/auth.py")

    # Minimal package stubs so auth.py can resolve relative imports / patches
    _ensure_package("superset")
    _ensure_package("superset.mcp_service")
    _ensure_package("superset.mcp_service.mcp_config")
    _ensure_package("superset.extensions")
    _ensure_package("superset.connectors")
    _ensure_package("superset.connectors.sqla")
    _ensure_package("superset.connectors.sqla.models")
    _ensure_package("superset.mcp_service.chart")
    _ensure_package("superset.mcp_service.chart.chart_utils")

    # Stub default_user_resolver used by _username_from_claims
    mcp_config = sys.modules["superset.mcp_service.mcp_config"]

    def _default_user_resolver(app, access_token):
        if hasattr(access_token, "subject") and access_token.subject:
            return access_token.subject
        if hasattr(access_token, "payload") and isinstance(access_token.payload, dict):
            return (
                access_token.payload.get("sub")
                or access_token.payload.get("username")
            )
        return None

    mcp_config.default_user_resolver = _default_user_resolver  # type: ignore[attr-defined]

    # Stub security_manager on superset package
    superset_pkg = sys.modules["superset"]
    if not hasattr(superset_pkg, "security_manager"):
        superset_pkg.security_manager = MagicMock()  # type: ignore[attr-defined]

    # Stub db.session for load_user_with_relationships if ever called unmocked
    extensions = sys.modules["superset.extensions"]
    if not hasattr(extensions, "db"):
        extensions.db = MagicMock()  # type: ignore[attr-defined]

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    setattr(sys.modules["superset.mcp_service"], "auth", module)
    spec.loader.exec_module(module)
    return module


def _app(**config) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
    return app


def test_claims_load_user_and_bind_active_post():
    """AccessToken claims with sub + active_post_id load user and bind post."""
    auth = _load_auth()
    app = _app(MCP_AUTH_ENABLED=True)
    user = MagicMock(username="alice")
    claims = {"sub": "alice", "active_post_id": 7}
    mock_sm = MagicMock()
    mock_sm.get_user_posts.return_value = [MagicMock(id=7)]

    with app.app_context():
        with (
            patch.object(auth, "_access_token_claims", return_value=claims),
            patch.object(
                auth, "load_user_with_relationships", return_value=user
            ) as mock_load,
            patch("superset.security_manager", mock_sm),
        ):
            result = auth.get_user_from_request()

        assert result is user
        mock_load.assert_called_once_with("alice")
        assert g.mcp_active_post_id == 7
        mock_sm.get_user_posts.assert_called_once_with(user)


def test_auth_enabled_no_jwt_does_not_fall_back_to_dev_username():
    """When MCP_AUTH_ENABLED, missing JWT must not use MCP_DEV_USERNAME."""
    auth = _load_auth()
    app = _app(MCP_AUTH_ENABLED=True, MCP_DEV_USERNAME="admin")

    with app.app_context():
        g.pop("user", None)
        with patch.object(auth, "_access_token_claims", return_value=None):
            with pytest.raises(ValueError, match="MCP_AUTH_ENABLED"):
                auth.get_user_from_request()


def test_unassigned_active_post_id_raises():
    """Invalid / unassigned active_post_id raises ValueError."""
    auth = _load_auth()
    app = _app(MCP_AUTH_ENABLED=True)
    user = MagicMock(username="alice")
    claims = {"sub": "alice", "active_post_id": 99}
    mock_sm = MagicMock()
    mock_sm.get_user_posts.return_value = [MagicMock(id=7)]

    with app.app_context():
        with (
            patch.object(auth, "_access_token_claims", return_value=claims),
            patch.object(auth, "load_user_with_relationships", return_value=user),
            patch("superset.security_manager", mock_sm),
        ):
            with pytest.raises(ValueError, match="not assigned"):
                auth.get_user_from_request()


def test_auth_enabled_missing_active_post_id_raises():
    """When auth is enabled, JWT without active_post_id fails closed."""
    auth = _load_auth()
    app = _app(MCP_AUTH_ENABLED=True)
    user = MagicMock(username="alice")
    claims = {"sub": "alice"}
    mock_sm = MagicMock()

    with app.app_context():
        with (
            patch.object(auth, "_access_token_claims", return_value=claims),
            patch.object(auth, "load_user_with_relationships", return_value=user),
            patch("superset.security_manager", mock_sm),
        ):
            with pytest.raises(ValueError, match="active_post_id"):
                auth.get_user_from_request()


def test_dev_username_used_when_auth_disabled():
    """When MCP_AUTH_ENABLED is False, fall back to MCP_DEV_USERNAME."""
    auth = _load_auth()
    app = _app(MCP_AUTH_ENABLED=False, MCP_DEV_USERNAME="devuser")
    user = MagicMock(username="devuser")

    with app.app_context():
        g.pop("user", None)
        with (
            patch.object(auth, "_access_token_claims", return_value=None),
            patch.object(
                auth, "load_user_with_relationships", return_value=user
            ) as mock_load,
        ):
            result = auth.get_user_from_request()

        assert result is user
        mock_load.assert_called_once_with("devuser")


def test_bearer_decode_fallback_binds_post():
    """Authorization Bearer decode with MCP_JWT_SECRET binds active_post_id."""
    import jwt

    auth = _load_auth()
    secret = "test-secret"
    app = _app(
        MCP_AUTH_ENABLED=True,
        MCP_JWT_SECRET=secret,
        MCP_JWT_ALGORITHM="HS256",
    )
    token = jwt.encode(
        {"sub": "bob", "active_post_id": 3},
        secret,
        algorithm="HS256",
    )
    user = MagicMock(username="bob")
    mock_sm = MagicMock()
    mock_sm.get_user_posts.return_value = [MagicMock(id=3)]

    with app.test_request_context(
        "/",
        headers={"Authorization": f"Bearer {token}"},
    ):
        with (
            patch(
                "fastmcp.server.dependencies.get_access_token",
                side_effect=RuntimeError("no token context"),
            ),
            patch.object(auth, "load_user_with_relationships", return_value=user),
            patch("superset.security_manager", mock_sm),
        ):
            result = auth.get_user_from_request()

        assert result is user
        assert g.mcp_active_post_id == 3

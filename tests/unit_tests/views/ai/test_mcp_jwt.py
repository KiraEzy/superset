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
"""Unit tests for post-scoped MCP JWT minting.

Loads ``mcp_jwt.py`` by file path so collection does not execute
``superset.views`` package init (requires a fully initialized app).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import jwt
import pytest

_MODULE_NAME = "superset.views.ai.mcp_jwt"


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


def _load_mcp_jwt() -> ModuleType:
    if _MODULE_NAME in sys.modules and hasattr(sys.modules[_MODULE_NAME], "mint_mcp_user_token"):
        return sys.modules[_MODULE_NAME]

    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "superset" / "views" / "ai" / "mcp_jwt.py"
    if not path.is_file():
        path = Path("/app/superset/views/ai/mcp_jwt.py")

    # Real ``superset`` package (for security_manager), stub views packages only.
    import superset as superset_pkg  # noqa: F401

    _ensure_package("superset.views")
    _ensure_package("superset.views.ai")

    if not hasattr(superset_pkg, "security_manager"):
        superset_pkg.security_manager = MagicMock()  # type: ignore[attr-defined]

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    setattr(sys.modules["superset.views.ai"], "mcp_jwt", module)
    spec.loader.exec_module(module)
    return module


def test_mint_requires_active_post():
    mcp_jwt = _load_mcp_jwt()
    user = MagicMock(username="creator")
    with pytest.raises(mcp_jwt.McpJwtError, match="active post"):
        mcp_jwt.mint_mcp_user_token(user=user, active_post_id=None)


def test_mint_requires_jwt_secret():
    mcp_jwt = _load_mcp_jwt()
    user = MagicMock(username="creator")
    mock_sm = MagicMock()
    mock_sm.get_user_posts.return_value = [MagicMock(id=7)]
    with (
        patch("superset.security_manager", mock_sm),
        patch.object(mcp_jwt, "_jwt_ttl_seconds", return_value=120),
        patch.object(mcp_jwt, "_jwt_issuer", return_value=None),
        patch.object(mcp_jwt, "_jwt_audience", return_value=None),
        patch.object(
            mcp_jwt,
            "_jwt_secret",
            side_effect=mcp_jwt.McpJwtError("MCP_JWT_SECRET is not configured"),
        ),
    ):
        with pytest.raises(mcp_jwt.McpJwtError, match="MCP_JWT_SECRET"):
            mcp_jwt.mint_mcp_user_token(user=user, active_post_id=7)


def test_mint_includes_claims_and_ttl():
    mcp_jwt = _load_mcp_jwt()
    user = MagicMock(username="creator")
    mock_sm = MagicMock()
    mock_sm.get_user_posts.return_value = [MagicMock(id=7)]
    with (
        patch.object(mcp_jwt, "_jwt_secret", return_value="test-secret"),
        patch.object(mcp_jwt, "_jwt_algorithm", return_value="HS256"),
        patch.object(mcp_jwt, "_jwt_ttl_seconds", return_value=120),
        patch.object(mcp_jwt, "_jwt_issuer", return_value="focal-bi"),
        patch.object(mcp_jwt, "_jwt_audience", return_value="superset-mcp"),
        patch("superset.security_manager", mock_sm),
    ):
        token = mcp_jwt.mint_mcp_user_token(user=user, active_post_id=7)

    claims = jwt.decode(
        token,
        "test-secret",
        algorithms=["HS256"],
        audience="superset-mcp",
        issuer="focal-bi",
    )
    assert claims["sub"] == "creator"
    assert claims["active_post_id"] == 7
    assert claims["exp"] - claims["iat"] == 120


def test_mint_rejects_unassigned_post():
    mcp_jwt = _load_mcp_jwt()
    user = MagicMock(username="creator")
    mock_sm = MagicMock()
    mock_sm.get_user_posts.return_value = [MagicMock(id=3)]
    with patch("superset.security_manager", mock_sm):
        with pytest.raises(mcp_jwt.McpJwtError, match="not assigned"):
            mcp_jwt.mint_mcp_user_token(user=user, active_post_id=7)

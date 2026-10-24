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
"""Focused destination, token isolation and OAuth error-path checks."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load this unit with model/config fakes so tests never initialize an application,
# contact servers, or discover credentials.
_spec = importlib.util.spec_from_file_location(
    "connections_unit",
    Path(__import__("superset").__file__).parent / "ai_runtime" / "connections.py",
)
_module = importlib.util.module_from_spec(_spec)
with patch.dict(
    sys.modules,
    {
        "superset.models.ai_runtime_connections": MagicMock(),
        "superset.views.ai": MagicMock(),
    },
):
    _spec.loader.exec_module(_module)
ConnectionError = _module.ConnectionError
_exchange = _module._exchange
validate_destination = _module.validate_destination


def _dns(address):
    return [(2, 1, 6, "", (address, 443))]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/mcp",
        "https://user:pass@example.com/mcp",
        "https://example.com/mcp#token",
        "file:///etc/passwd",
    ],
)
def test_unsafe_url_forms_rejected(url):
    with pytest.raises(ConnectionError):
        validate_destination(url)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fe80::1"]
)
def test_private_dns_answers_rejected(address):
    with patch.object(_module.socket, "getaddrinfo", return_value=_dns(address)):
        with pytest.raises(ConnectionError):
            validate_destination("https://example.com/mcp")


def test_admin_private_exception_is_explicit():
    with patch.object(_module.socket, "getaddrinfo", return_value=_dns("127.0.0.1")):
        assert (
            validate_destination("http://localhost/mcp", True) == "http://localhost/mcp"
        )


def test_accepted_turn_pins_mcp_destination_and_its_credentials():
    from flask import Flask
    from types import SimpleNamespace

    live = {
        "mcpEnabled": True,
        "mcpServerUrl": "https://new.example/mcp",
        "mcpBearerToken": "new-test-token",
    }
    snapshot = {
        "mcpServerUrl": "https://original.example/mcp",
        "mcpBearerToken": "original-test-token",
    }
    app = Flask(__name__)
    with (
        app.app_context(),
        patch.object(_module.config_store, "resolve_active_config", return_value=live),
        patch.dict(
            sys.modules,
            {
                "superset.views.ai.proxy": SimpleNamespace(
                    normalize_mcp_url=lambda url: url
                )
            },
        ),
    ):
        result = _module.resolve_connections(
            ["focalbi"], 12, 34, focal_config=snapshot
        )[0]
    assert result["url"] == snapshot["mcpServerUrl"]
    assert result["bearer_token"] == snapshot["mcpBearerToken"]
    assert live["mcpServerUrl"] == "https://new.example/mcp"


def test_disabling_global_mcp_still_blocks_a_pinned_turn():
    from flask import Flask
    from types import SimpleNamespace

    app = Flask(__name__)
    with (
        app.app_context(),
        patch.object(
            _module.config_store,
            "resolve_active_config",
            return_value={"mcpEnabled": False},
        ),
        patch.dict(
            sys.modules,
            {
                "superset.views.ai.proxy": SimpleNamespace(
                    normalize_mcp_url=lambda url: url
                )
            },
        ),
    ):
        with pytest.raises(ConnectionError, match="disabled"):
            _module.resolve_connections(
                ["focalbi"],
                12,
                34,
                focal_config={"mcpServerUrl": "https://original.example/mcp"},
            )


def test_all_dns_answers_checked():
    with patch.object(
        _module.socket, "getaddrinfo", return_value=_dns("8.8.8.8") + _dns("127.0.0.1")
    ):
        with pytest.raises(ConnectionError):
            validate_destination("https://example.com")


def test_exchange_never_follows_redirects_and_hides_provider_errors():
    row = MagicMock(allow_private=False)
    response = MagicMock(status_code=302)
    with (
        patch.object(_module, "validate_destination"),
        patch.object(_module.requests, "post", return_value=response) as post,
    ):
        with pytest.raises(ConnectionError, match="OAuth token exchange failed"):
            _exchange(
                row,
                {"token_endpoint": "https://example.com/token"},
                {"code": "private-code"},
            )
        assert post.call_args.kwargs["allow_redirects"] is False


def test_account_query_binds_connection_actor_and_post():
    _account = _module._account
    with patch.object(_module, "db") as database:
        _account("connection-id", 12, 34)
        database.session.query.return_value.filter_by.assert_called_once_with(
            connection_id="connection-id", user_id=12, post_id=34
        )


def test_catalogue_returns_no_account_credentials():
    list_connections = _module.list_connections
    row = MagicMock(id="server", label="Service", auth_type="token")
    with (
        patch.object(
            _module.config_store,
            "resolve_active_config",
            return_value={"mcpEnabled": False},
        ),
        patch.object(_module, "db") as database,
        patch.object(_module, "_account", return_value=MagicMock(credentials="secret")),
    ):
        database.session.query.return_value.filter_by.return_value.all.return_value = [
            row
        ]
        result = list_connections(12, 34)
        assert result == [
            {
                "id": "server",
                "label": "Service",
                "auth_type": "token",
                "linked": True,
                "status": "connected",
            }
        ]


@pytest.mark.parametrize("mode", ["missing", "expired", "other_post"])
def test_oauth_state_rejects_unbound_or_expired_attempt_without_http(mode):
    from datetime import datetime, timedelta

    pending = (
        None
        if mode == "missing"
        else MagicMock(
            expires_on=datetime.utcnow()
            + timedelta(minutes=-1 if mode == "expired" else 1),
            post_id=999 if mode == "other_post" else 34,
        )
    )
    with (
        patch.object(_module, "db") as database,
        patch.object(_module.requests, "post") as http,
    ):
        database.session.query.return_value.filter_by.return_value.with_for_update.return_value.one_or_none.return_value = pending
        with pytest.raises(ConnectionError, match="expired or does not belong"):
            _module.finish_oauth(
                "state", "code", 12, "https://app.example/callback", post_id=34
            )
        database.session.query.return_value.filter_by.assert_called_once_with(
            state="state", user_id=12
        )
        http.assert_not_called()


def test_callback_redirect_mismatch_never_exchanges_code():
    from datetime import datetime, timedelta

    pending = MagicMock(
        expires_on=datetime.utcnow() + timedelta(minutes=1),
        post_id=34,
        redirect_uri="https://app.example/callback",
    )
    with (
        patch.object(_module, "db") as database,
        patch.object(_module, "get_connection"),
        patch.object(
            _module, "_oauth", return_value={"redirect_uri": pending.redirect_uri}
        ),
        patch.object(_module.requests, "post") as http,
    ):
        database.session.query.return_value.filter_by.return_value.with_for_update.return_value.one_or_none.return_value = pending
        with pytest.raises(ConnectionError, match="does not match"):
            _module.finish_oauth(
                "state", "code", 12, "https://attacker.example/callback", post_id=34
            )
        http.assert_not_called()

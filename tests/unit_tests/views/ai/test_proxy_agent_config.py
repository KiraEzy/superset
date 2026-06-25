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
from superset.views.ai.proxy import (
    AGENT_SYSTEM_PROMPT,
    MAX_TOOL_ITERATIONS,
    _resolve_agent_max_iterations,
    _resolve_agent_system_prompt,
    rewrite_superset_url_for_client,
)


def test_resolve_agent_max_iterations_prefers_request_value(app_context) -> None:
    with app_context:
        assert _resolve_agent_max_iterations(42) == 42


def test_resolve_agent_max_iterations_uses_config(app_context) -> None:
    with app_context:
        from flask import current_app

        current_app.config["AI_AGENT_MAX_ITERATIONS"] = 80
        assert _resolve_agent_max_iterations(None) == 80


def test_resolve_agent_max_iterations_default(app_context) -> None:
    with app_context:
        from flask import current_app

        current_app.config.pop("AI_AGENT_MAX_ITERATIONS", None)
        assert _resolve_agent_max_iterations(None) == MAX_TOOL_ITERATIONS
        assert MAX_TOOL_ITERATIONS == 120


def test_resolve_agent_system_prompt_prefers_request_value(app_context) -> None:
    with app_context:
        assert _resolve_agent_system_prompt("Custom prompt") == "Custom prompt"


def test_resolve_agent_system_prompt_uses_config(app_context) -> None:
    with app_context:
        from flask import current_app

        current_app.config["AI_AGENT_SYSTEM_PROMPT"] = "Config prompt"
        assert _resolve_agent_system_prompt("") == "Config prompt"
        assert _resolve_agent_system_prompt(None) == "Config prompt"


def test_resolve_agent_system_prompt_default(app_context) -> None:
    with app_context:
        from flask import current_app

        current_app.config.pop("AI_AGENT_SYSTEM_PROMPT", None)
        assert _resolve_agent_system_prompt("") == AGENT_SYSTEM_PROMPT


def test_rewrite_superset_url_for_client_relative(app) -> None:
    with app.test_request_context(
        base_url="http://192.168.11.122:9000/",
        headers={"Host": "192.168.11.122:9000"},
    ):
        assert (
            rewrite_superset_url_for_client("/explore/?slice_id=42")
            == "http://192.168.11.122:9000/explore/?slice_id=42"
        )


def test_rewrite_superset_url_for_client_localhost(app) -> None:
    with app.test_request_context(
        base_url="http://192.168.11.122:9000/",
        headers={"Host": "192.168.11.122:9000"},
    ):
        assert (
            rewrite_superset_url_for_client("http://localhost:9000/explore/?slice_id=42")
            == "http://192.168.11.122:9000/explore/?slice_id=42"
        )


def test_rewrite_superset_url_for_client_without_request() -> None:
    assert (
        rewrite_superset_url_for_client("http://localhost:9000/explore/?slice_id=42")
        == "http://localhost:9000/explore/?slice_id=42"
    )

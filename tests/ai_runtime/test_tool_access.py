# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Restrictions never grant access and malformed policy cannot silently reset it."""

import pytest

from superset.ai_runtime.tool_access import allowed_tools, normalize_policy


def test_role_union_is_narrowed_by_user_rule():
    policy = normalize_policy(
        {
            "roles": {"Analyst": ["health_check"], "Author": ["generate_chart"]},
            "users": {"alice": ["health_check", "execute_sql"]},
        }
    )
    assert allowed_tools(policy, "alice", {"Analyst", "Author"}) == {"health_check"}
    assert allowed_tools(policy, "bob", {"Analyst", "Author"}) == {
        "health_check",
        "generate_chart",
    }
    assert allowed_tools(policy, "bob", {"Viewer"}) is None


def test_empty_rule_blocks_tools_and_unconfigured_policy_preserves_native_access():
    assert (
        allowed_tools(normalize_policy({"users": {"alice": []}}), "alice", set())
        == set()
    )
    assert (
        allowed_tools(
            normalize_policy({"roles": {"Analyst": []}}), "alice", {"Analyst"}
        )
        == set()
    )
    assert allowed_tools(normalize_policy({}), "alice", {"Admin"}) is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"unknown": {}},
        {"roles": []},
        {"users": {"alice": "all"}},
        {"users": {"alice": [1]}},
        {"users": {"": []}},
    ],
)
def test_invalid_policy_is_rejected(value):
    with pytest.raises(ValueError):
        normalize_policy(value)

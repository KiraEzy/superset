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
from superset.views.ai.proxy import _extract_chart_payload


def test_extract_chart_payload_success() -> None:
    raw_result = {
        "structuredContent": {
            "success": True,
            "form_data": {"viz_type": "pie", "datasource": "1__table"},
            "form_data_key": "abc123",
            "explore_url": "/explore/?slice_id=42",
            "chart": {"id": 42, "slice_name": "Revenue", "viz_type": "pie"},
            "previews": {"vega_lite": {"type": "vega_lite"}},
        }
    }
    payload = _extract_chart_payload("generate_chart", raw_result)
    assert payload is not None
    assert payload["slice_id"] == 42
    assert payload["title"] == "Revenue"
    assert payload["viz_type"] == "pie"
    assert payload["form_data_key"] == "abc123"
    assert "previews" not in payload


def test_extract_chart_payload_ignores_non_chart_tool() -> None:
    assert _extract_chart_payload("execute_sql", {"success": True}) is None


def test_extract_chart_payload_failure() -> None:
    raw_result = {
        "structuredContent": {
            "success": False,
            "form_data": {"viz_type": "pie"},
        }
    }
    assert _extract_chart_payload("generate_chart", raw_result) is None


def test_extract_chart_payload_missing_form_data() -> None:
    raw_result = {
        "structuredContent": {
            "success": True,
            "chart": {"id": 1, "viz_type": "pie"},
        }
    }
    assert _extract_chart_payload("generate_chart", raw_result) is None

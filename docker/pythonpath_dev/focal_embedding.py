# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from superset.config import TALISMAN_CONFIG as BASE_TALISMAN_CONFIG
from superset.config import TALISMAN_DEV_CONFIG as BASE_TALISMAN_DEV_CONFIG

_secret_file = Path(__file__).resolve().parents[1] / ".focal-embed-secret.local"

# Opt in only on installations provisioned by embedded-demo/setup.ps1.
if _secret_file.is_file():
    FEATURE_FLAGS = {
        "ALERT_REPORTS": True,
        "DATASET_FOLDERS": True,
        "EMBEDDED_SUPERSET": True,
    }
    GUEST_TOKEN_JWT_SECRET = _secret_file.read_text(encoding="utf-8").strip()
    if len(GUEST_TOKEN_JWT_SECRET) < 32:
        raise ValueError("FocalBI embedding requires a strong signing secret")
    GUEST_TOKEN_JWT_ALGO = "HS256"  # noqa: S105 -- algorithm identifier, not a secret
    GUEST_TOKEN_JWT_AUDIENCE = "focalbi-embedded"  # noqa: S105 -- public audience
    GUEST_TOKEN_JWT_EXP_SECONDS = 300
    GUEST_ROLE_NAME = "EmbeddedViewer"

    TALISMAN_CONFIG = deepcopy(BASE_TALISMAN_CONFIG)
    TALISMAN_DEV_CONFIG = deepcopy(BASE_TALISMAN_DEV_CONFIG)
    for _policy in (TALISMAN_CONFIG, TALISMAN_DEV_CONFIG):
        _policy["frame_options"] = None
        _csp = cast(dict[str, Any], _policy["content_security_policy"])
        _csp["frame-ancestors"] = [
            "'self'",
            "http://localhost:3100",
            "http://localhost:3010",
            "http://192.168.10.27:3010",
        ]

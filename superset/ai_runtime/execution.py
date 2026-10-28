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
"""Versioned execution selection without importing optional worker dependencies."""

import logging

SDK_VERSION = "0.10.5"
OPENAI_CLIENT_VERSION = "2.19.0"


class _SdkLogFilter(logging.Filter):
    """Suppress SDK diagnostics that would serialize conversation input."""

    def filter(self, record: logging.LogRecord) -> bool:
        if "filtered.input=" in str(record.msg):
            record.msg = "Agents SDK request failed; inspect the authorized turn ledger"
            record.args = ()
        return True


def protect_sdk_logs() -> None:
    """Install one filter for SDK error messages; tracing is disabled separately."""
    logger = logging.getLogger("openai.agents")
    if not any(isinstance(item, _SdkLogFilter) for item in logger.filters):
        logger.addFilter(_SdkLogFilter())

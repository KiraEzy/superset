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
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX = "navbar_display_name_max_width_px"


@dataclass(frozen=True)
class KnownKey:
    key: str
    value_type: str  # "int" | "str"
    default: Any
    public: bool
    min_value: int | None = None
    max_value: int | None = None


KNOWN_KEYS: dict[str, KnownKey] = {
    KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX: KnownKey(
        key=KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
        value_type="int",
        default=64,
        public=True,
        min_value=32,
        max_value=400,
    ),
}


def get_default(key: str) -> Any:
    return KNOWN_KEYS[key].default


def is_known(key: str) -> bool:
    return key in KNOWN_KEYS


def is_public(key: str) -> bool:
    return key in KNOWN_KEYS and KNOWN_KEYS[key].public


def parse_and_validate(key: str, raw: Any) -> Any:
    """Validate known keys; for unknown keys return stripped string."""
    if key not in KNOWN_KEYS:
        if raw is None:
            raise ValueError("value is required")
        return str(raw)

    meta = KNOWN_KEYS[key]
    if meta.value_type == "int":
        if isinstance(raw, bool) or raw is None:
            raise ValueError(f"{key} must be an integer")
        if isinstance(raw, float) and not raw.is_integer():
            raise ValueError(f"{key} must be an integer")
        try:
            value = int(raw)
        except (TypeError, ValueError) as ex:
            raise ValueError(f"{key} must be an integer") from ex
        if meta.min_value is not None and value < meta.min_value:
            raise ValueError(f"{key} must be >= {meta.min_value}")
        if meta.max_value is not None and value > meta.max_value:
            raise ValueError(f"{key} must be <= {meta.max_value}")
        return value

    return str(raw)


def serialize_value(key: str, value: Any) -> str:
    if key in KNOWN_KEYS and KNOWN_KEYS[key].value_type == "int":
        return str(int(value))
    return str(value)


def deserialize_stored(key: str, stored: str) -> Any:
    if key in KNOWN_KEYS and KNOWN_KEYS[key].value_type == "int":
        return int(stored)
    return stored

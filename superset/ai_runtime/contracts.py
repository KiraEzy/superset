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
"""Provider-neutral runtime contracts; no Flask or MCP server imports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from superset.utils import json


class AiRuntimeError(Exception):
    """An error safe to expose without upstream response bodies or credentials."""

    def __init__(
        self, message: str, *, code: str = "runtime_error", source: str = "agent"
    ) -> None:
        super().__init__(message)
        self.code, self.source = code, source
        self.retryable = False
        self.validation: dict[str, Any] = {}

    def to_event(self) -> dict[str, Any]:
        """Return a transport-neutral error."""
        return {"message": str(self), "code": self.code, "source": self.source}


class TurnCancelledError(AiRuntimeError):
    """The user cancelled the active turn."""


@dataclass
class Tool:
    """An advertised name mapped to exactly one reviewed connection and tool."""

    name: str
    original_name: str
    connection: dict[str, Any]
    schema: dict[str, Any]
    description: str = ""
    effect: str = "unknown"
    annotations: dict[str, Any] = field(default_factory=dict)

    @property
    def schema_hash(self) -> str:
        """Stable identity of the server's unchanged canonical JSON schema."""
        return hashlib.sha256(
            json.dumps(self.schema, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def definition(self) -> dict[str, Any]:
        """Return a lossless Chat Completions tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }


@dataclass
class Generation:
    """One completed streaming model generation, including continuation state."""

    content: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    continuation: dict[str, Any] = field(default_factory=dict)
    # Opaque protocol fields are encrypted in checkpoints, never sent to the UI.
    provider_fields: dict[str, Any] = field(default_factory=dict)


ASK_USER: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Pause this turn for a necessary BI clarification when "
            "evidence cannot resolve "
            "the user's intent. question is the complete user-facing question; options "
            "are optional mutually exclusive answer suggestions. Do"
            " not use for routine "
            "progress or facts obtainable from permitted tools. The"
            " runtime persists the "
            "question and resumes the same turn after the user "
            "answers; read the returned "
            "tool message {answer: string} as the user's answer, not "
            "permission to expand action scope."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1},
                "options": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
}

READ_EVIDENCE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_evidence",
        "description": (
            "Retrieve an omitted field or next page from a full tool result already "
            "recorded in THIS conversation; this is a local read, not a new BI query. "
            "Use only when the visible preview lacks information needed to answer. "
            "A discovery preview with all page IDs/names is "
            "sufficient for a catalogue overview. Once the dataset ID is visible, use "
            "get_dataset_info for its columns and metrics; rereading names is not "
            "schema inspection. "
            "Copy read_examples or next_read exactly. call_id is "
            "the original evidence_ref, "
            "not the ID of a read_evidence page. path starts at the"
            " normalized source data "
            "root: for available_paths=[datasets,total_count], use [datasets], NOT "
            "[result,datasets] or [data,datasets]. [] inspects root"
            " keys; strings in path "
            "can address dictionary keys or zero-based array indices. "
            "Success returns isError=false, data (the selected bounded page), "
            "source_evidence_ref (original source), offset (zero-based start), total "
            "(number of list entries, dictionary keys, or string "
            "characters at this path; "
            "NOT the server catalogue total_count), next_offset "
            "(actual next start, or null), "
            "next_read (exact arguments for the next page, or "
            "null), truncated (some fields "
            "are excerpted; retrieve a deeper path if needed), "
            "available_paths (keys at "
            "the selected path; append one to the current path), "
            "and note (coverage guidance). "
            "The returned page can be shorter than limit because of the byte budget. "
            "Do not compute the next offset yourself; follow next_read. isError=true "
            "returns message plus root available_paths; correct the"
            " path, do not repeat it. "
            "message:N references a historical conversation "
            "message; use path [content] "
            "for its visible text. Evidence never grants permission"
            " or approves an action."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "call_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 256,
                    "description": (
                        "Original evidence_ref/tool call ID from the "
                        "source preview, or message:N. Keep this source"
                        " for every page."
                    ),
                },
                "path": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 12,
                    "description": (
                        "Keys from the original normalized data root. "
                        "Example: [datasets]. Omit or [] to inspect the"
                        " root. No preview wrapper prefixes."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Zero-based start within the selected source "
                        "value. Default 0. Copy next_read.offset for "
                        "subsequent pages."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": (
                        "Maximum entries/keys/characters requested, "
                        "default 20; the actual returned page may be "
                        "smaller. Use next_read rather than offset + "
                        "limit."
                    ),
                },
            },
            "required": ["call_id"],
            "additionalProperties": False,
        },
    },
}


READ_ARTIFACT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_artifact",
        "description": (
            "Load the latest permitted chart or exact artifact_id from this "
            "conversation before modifying its style/data. Returns isError=false "
            "and structuredContent with data (paged artifact fields) and total "
            "(number of selected keys/entries), plus offset for list/text pages. "
            "Artifact fields: id/title identify the chart; payload.form_data "
            "contains native chart settings; payload.form_data_key is a temporary"
            " preview locator; source_request contains original tool arguments "
            "and config; saved distinguishes a permanent BI chart from a preview;"
            " version and provenance identify its revision and source "
            "connection/tool. path is relative to the artifact, e.g. "
            "[payload,form_data], never the response's structuredContent/data "
            "wrapper. Omit path to read its root. isError=true with message means"
            " unavailable/unauthorized artifact or invalid path. Use "
            "source_request.config as the modification baseline; preserve "
            "dataset, metrics and filters unless asked to change them. Preview "
            "IDs are not saved chart IDs. For previews use update_chart_preview "
            "or generate_explore_link. Retrieval does not authorize writes; "
            "explain unsupported styles honestly. For a scalar path, "
            "structuredContent is the scalar itself, without a data/total paging "
            "wrapper."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": (
                        "Stable conversation artifact ID from the chart"
                        " index. Omit to load the latest permitted "
                        "chart."
                    ),
                },
                "path": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 12,
                    "description": (
                        "Keys from the artifact root, e.g. "
                        "[payload,form_data]. Array indices are "
                        "zero-based strings."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Zero-based start among keys, list entries or "
                        "text characters at path. Default 0."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": (
                        "Maximum keys, entries or characters to return. Default 20."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
}


PRESENT_DELIVERABLE = {
    "function": {
        "name": "present_deliverable",
        "description": (
            "Present a completed chart preview or result table in Deliverables. "
            "Use an artifact_id from a successful BI tool. Do not present "
            "diagnostic queries, raw SQL or intermediate previews. Saved charts and "
            "dashboards appear automatically. Optionally replace a prior presented "
            "artifact of the same type. This changes presentation only; "
            "it never saves BI data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string", "minLength": 1, "maxLength": 256},
                "title": {"type": "string", "minLength": 1, "maxLength": 256},
                "replaces_artifact_id": {"type": "string", "maxLength": 256},
            },
            "required": ["artifact_id", "title"],
            "additionalProperties": False,
        },
    }
}

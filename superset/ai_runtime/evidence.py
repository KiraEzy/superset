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
"""Canonical evidence access and strictly bounded, disposable model previews."""

from __future__ import annotations

from typing import Any

from superset.utils import json


def data_root(value: Any) -> Any:
    """Resolve an MCP envelope without modifying its authoritative wire record."""
    if not isinstance(value, dict):
        return value
    structured = value.get("structuredContent", value.get("structured_content"))
    if structured is not None:
        return structured
    blocks = value.get("content")
    if isinstance(blocks, list):
        decoded = []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            try:
                parsed = json.loads(block.get("text", ""))
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, (dict, list)):
                decoded.append(parsed)
        # Do not silently discard additional blocks when a tool returns several.
        if len(blocks) == len(decoded) == 1:
            return decoded[0]
        if decoded:
            return {"blocks": blocks}
    return {key: item for key, item in value.items() if key != "raw"}


def paths(value: Any) -> list[str]:
    """Advertise keys relative to the evidence data root."""
    return (
        [str(key) for key in list(value)[:20] if len(str(key)) <= 128]
        if isinstance(value, dict)
        else []
    )


def discovery_records(value: Any) -> list[dict[str, Any]]:
    """Find direct resource lists without inferring nested coverage."""
    root = data_root(value)
    arrays = list(root.values()) if isinstance(root, dict) else [root]
    return [
        item
        for array in arrays
        if isinstance(array, list)
        for item in array
        if isinstance(item, dict) and "id" in item
    ]


def _project(item: Any, width: int, text: int, depth: int = 0) -> Any:
    """Recursively project one candidate preview."""
    if depth > 8:
        return {"omitted": "Retrieve a deeper evidence path"}
    if isinstance(item, str):
        return item if len(item) <= text else item[:text] + " [excerpt]"
    if isinstance(item, list):
        result = [_project(child, width, text, depth + 1) for child in item[:width]]
        if len(item) > width:
            result.append({"omitted_items": len(item) - width})
        return result
    if isinstance(item, dict):
        keys = list(item)
        mapping = {
            str(key)[:160]: _project(item[key], width, text, depth + 1)
            for key in keys[:width]
            if key not in {"base64", "image_data", "reasoning_content"}
            and not str(key).startswith("_")
        }
        if len(keys) > width:
            mapping["omitted_keys"] = len(keys) - width
        return mapping
    return item


def bounded(value: Any, max_chars: int = 5000) -> tuple[Any, bool]:
    """Bound strings, arrays, mappings and nesting, with explicit omission markers."""

    def dump(item: Any) -> str:
        return json.dumps(item, default=str)

    for width, text in ((100, 600), (30, 300), (10, 160), (3, 80), (1, 40)):
        preview = _project(value, width, text)
        if len(dump(preview)) <= max_chars:
            return preview, dump(preview) != dump(value)
    return {"omitted": "Retrieve a more specific evidence path"}, True


def _cursor(value: Any) -> dict[str, Any] | None:
    """Do not let an unusually long evidence path enlarge a bounded reply."""
    return value if isinstance(value, dict) and len(json.dumps(value)) <= 1000 else None


def read_page(
    raw: Any, args: dict[str, Any], *, historical: bool = False
) -> dict[str, Any]:
    """Read canonical paths, retaining legacy explicit envelope paths for clients."""
    root = raw if historical else data_root(raw)
    requested = args.get("path", [])
    value = root
    # Existing explicit structuredContent/content paths remain addressable. New
    # previews always advertise paths relative to the normalized root.
    if (
        requested
        and isinstance(raw, dict)
        and requested[0]
        in {"structuredContent", "structured_content", "content", "raw"}
    ):
        value = raw
    try:
        for key in requested:
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, TypeError, ValueError):
        return {
            "isError": True,
            "message": (
                "Evidence path is unavailable; use a path relative to the data root."
            ),
            "available_paths": paths(root),
        }
    offset, limit = args.get("offset", 0), args.get("limit", 20)
    if isinstance(value, (list, str, dict)) and offset > 0 and offset >= len(value):
        return {
            "isError": True,
            "message": (
                "Offset is outside this evidence. Follow next_read on the source "
                "result; do not paginate a previously returned page as the full result."
            ),
            "available_paths": paths(root),
            "next_read": _cursor(raw.get("next_read"))
            if isinstance(raw, dict)
            else None,
        }
    next_offset = None
    selected: Any
    if isinstance(value, (list, str)):
        total = len(value)
        end = min(offset + limit, total)
        # Reduce the actual page length as needed rather than reporting a cursor
        # beyond entries omitted by preview projection.
        while end > offset + 1 and len(json.dumps(value[offset:end])) > 4200:
            end = offset + max(1, (end - offset) // 2)
        selected = value[offset:end]
        next_offset = end if end < total else None
    elif isinstance(value, dict):
        keys = list(value)
        total = len(keys)
        end = min(offset + limit, total)
        while (
            end > offset + 1
            and len(json.dumps({key: value[key] for key in keys[offset:end]})) > 4200
        ):
            end = offset + max(1, (end - offset) // 2)
        selected = {key: value[key] for key in keys[offset:end]}
        next_offset = end if end < total else None
    else:
        selected, total = value, 1
    preview, truncated = bounded(selected, 4200)
    response = {
        "isError": False,
        "data": preview,
        "source_evidence_ref": args.get("call_id")
        if len(str(args.get("call_id", ""))) <= 256
        else None,
        "offset": offset,
        "total": total,
        "next_offset": next_offset,
        "next_read": _cursor(
            {
                "call_id": args["call_id"],
                "path": requested,
                "offset": next_offset,
                "limit": limit,
            }
        )
        if next_offset is not None and args.get("call_id")
        else None,
        "truncated": truncated,
        "available_paths": paths(value),
        "note": "Use next_read for the next page and deeper paths for excerpted fields."
        if truncated
        else "Page of recorded evidence; not an authorization grant.",
    }
    if len(json.dumps(response)) > 6000:
        response["data"], _ = bounded(selected, 2500)
        response["available_paths"] = response["available_paths"][:8]
        response["truncated"] = True
    return response

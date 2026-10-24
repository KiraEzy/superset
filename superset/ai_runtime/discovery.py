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
"""Shared, checkpointed discovery progress; never an execution or permission cache."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from superset.utils import json

from .evidence import data_root, discovery_records

PRESENTATION = {
    "page",
    "page_size",
    "offset",
    "limit",
    "select_columns",
    "order_column",
    "order_direction",
    "sort",
    "sort_by",
}
REFRESH = {"refresh_metadata", "force_refresh"}
VOLATILE = {"timestamp", "changed_on", "created_on", "last_updated", "cache_hit"}


def key(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def membership(arguments: Any) -> Any:
    """Separate query membership from presentation without changing filter values."""
    if not isinstance(arguments, dict):
        return arguments
    body = arguments.get("request", arguments)
    if not isinstance(body, dict):
        return body
    return {
        k: v for k, v in body.items() if k not in PRESENTATION | REFRESH | {"use_cache"}
    }


def scope(name: str, arguments: Any, connection: str = "") -> str:
    return key([connection, name, membership(arguments)])


def fresh_state() -> dict[str, Any]:
    return {
        "version": 1,
        "queries": {},
        "resources": {},
        "reads": {},
        "blocked_generations": 0,
        "interventions": 0,
    }


def initialize(checkpoint: dict[str, Any]) -> dict[str, Any]:
    state = checkpoint.get("discovery")
    if not isinstance(state, dict) or state.get("version") != 1:
        state = checkpoint["discovery"] = fresh_state()
    return state


def request(tool: Any, args: dict[str, Any]) -> tuple[str, str, set[str], bool]:
    body = args.get("request", args)
    query = scope(tool.original_name, args, str(tool.connection["id"]))
    page = key(
        {k: v for k, v in body.items() if k in PRESENTATION - {"select_columns"}}
        | {"page": body.get("page", 1), "page_size": body.get("page_size", 10)}
    )
    projection = body.get("select_columns")
    fields = (
        set(projection)
        if isinstance(projection, list)
        and all(isinstance(field, str) for field in projection)
        else {key(["projection", projection])}
    )
    refresh = (
        any(body.get(k) is True for k in REFRESH) or body.get("use_cache") is False
    )
    return query, page, fields, refresh


def window(args: dict[str, Any]) -> tuple[int, int, str]:
    body = args.get("request", args)
    size = body.get("page_size", body.get("limit", 10))
    page_number = body.get("page", 1)
    if not isinstance(size, int) or not isinstance(page_number, int):
        return 0, 0, key(["opaque_position", args])
    start = body.get("offset", (page_number - 1) * size)
    if not isinstance(start, int):
        return 0, 0, key(["opaque_position", args])
    ordering = key(
        [
            body.get("order_column"),
            body.get("order_direction", "desc"),
            body.get("sort"),
            body.get("sort_by"),
        ]
    )
    return start, start + size, ordering


def duplicate(state: dict[str, Any], tool: Any, args: dict[str, Any]) -> str | None:
    if not tool.original_name.startswith("list_") or not isinstance(
        args.get("request", args), dict
    ):
        return None
    query, page, fields, refresh = request(tool, args)
    if refresh:
        return None
    pages = state["queries"].get(query, {}).get("pages", {})
    prior = pages.get(page)
    if prior and (not fields or fields <= set(prior["fields"])):
        return str(prior["evidence_ref"])
    if not tool.connection.get("is_focal"):
        return None  # External servers may use a different pagination convention.
    start, end, ordering = window(args)
    for covered in pages.values():
        if (
            covered.get("ordering") == ordering
            and covered.get("start", -1) <= start
            and start <= covered.get("end", -1)
            and min(
                end, covered["total"] if isinstance(covered.get("total"), int) else end
            )
            <= covered.get("end", -1)
            and (not fields or fields <= set(covered["fields"]))
        ):
            return str(covered["evidence_ref"])
    return None


def _next_page(entry: dict[str, Any], args: dict[str, Any], root: Any) -> None:
    if isinstance(root, dict) and isinstance(root.get("page"), int):
        page_number = root["page"]
        if page_number >= entry.get("last_page", 0):
            entry["last_page"] = page_number
            entry["next_arguments"] = None
            if root.get("has_next") is True:
                next_body = {
                    **args.get("request", args),
                    "page": page_number + 1,
                    "page_size": root.get("page_size", 10),
                }
                entry["next_arguments"] = (
                    {"request": next_body} if "request" in args else next_body
                )


def observe(
    state: dict[str, Any],
    tool: Any,
    args: dict[str, Any],
    value: Any,
    reference: str,
    input_text: str = "",
) -> bool:
    if not isinstance(args.get("request", args), dict):
        return False
    root = data_root(value)
    recorded_args = args
    if (
        isinstance(root, dict)
        and isinstance(root.get("page"), int)
        and isinstance(root.get("page_size"), int)
    ):
        body = {
            **args.get("request", args),
            "page": root["page"],
            "page_size": root["page_size"],
        }
        recorded_args = {"request": body} if "request" in args else body
    query, page, requested, refresh = request(tool, recorded_args)
    if refresh:
        state["queries"].pop(query, None)
    entry = state["queries"].setdefault(query, {"pages": {}, "matches": []})
    records = discovery_records(value)
    loaded = root.get("columns_loaded", []) if isinstance(root, dict) else []
    fields = requested | set(loaded) | set().union(*(set(r) for r in records))
    # Empty successful pages also establish that repeating the same projection
    # cannot discover another record. Explicit refresh remains possible.
    if not records:
        fields |= requested
    start, _, ordering = window(recorded_args)
    total = root.get("total_count") if isinstance(root, dict) else None
    prior_page = entry["pages"].get(page, {})
    fields |= set(prior_page.get("fields", []))
    references = list(dict.fromkeys(prior_page.get("evidence_refs", []) + [reference]))
    entry["pages"][page] = {
        "fields": sorted(fields),
        "evidence_ref": reference,
        "evidence_refs": references[-32:],
        "start": start,
        "end": start + len(records),
        "ordering": ordering,
        "total": total if isinstance(total, int) else prior_page.get("total"),
    }
    entry["tool_name"] = tool.name
    entry["connection_id"] = tool.connection["id"]
    _next_page(entry, args, root)
    body = args.get("request", args)
    terms = [body.get("search", "")]
    terms += [
        f.get("value", "")
        for f in body.get("filters", [])
        if f.get("col") == "table_name" and f.get("opr") == "eq"
    ]
    progress = False
    for record in records:
        rid = key([tool.connection["id"], tool.original_name, record["id"]])
        facts = {k: key(v) for k, v in record.items() if k not in VOLATILE}
        previous = state["resources"].get(rid, {})
        if any(k not in previous or previous[k] != v for k, v in facts.items()):
            progress = True
        state["resources"][rid] = {**previous, **facts}
        name = str(record.get("table_name", ""))
        if (
            tool.original_name == "list_datasets"
            and name
            and (
                any(
                    isinstance(t, str) and t.casefold() == name.casefold()
                    for t in terms
                )
                or re.search(
                    r"(?<!\w)"
                    + re.escape(re.sub(r"[_\W]+", " ", name).strip())
                    + r"(?!\w)",
                    re.sub(r"[_\W]+", " ", input_text).strip(),
                    re.I,
                )
            )
        ):
            match = {
                "connection_id": tool.connection["id"],
                "dataset_id": record["id"],
                "table_name": name,
                "schema": record.get("schema"),
                "database_name": record.get("database_name"),
                "evidence_ref": reference,
                "schema_inspected": False,
            }
            existing = next(
                (m for m in entry["matches"] if m["dataset_id"] == record["id"]), None
            )
            if existing:
                match["schema_inspected"] = existing["schema_inspected"]
                existing.update(match)
            else:
                entry["matches"].append(match)
    return progress


def matches(state: dict[str, Any]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, Any], dict[str, Any]] = {}
    for query in state["queries"].values():
        for match in query["matches"]:
            identity = (match["connection_id"], match["dataset_id"])
            previous = unique.get(identity)
            unique[identity] = {
                **match,
                "schema_inspected": match["schema_inspected"]
                or bool(previous and previous["schema_inspected"]),
            }
    return list(unique.values())


def inspect_dataset(
    state: dict[str, Any], tool: Any, args: dict[str, Any], value: Any = None
) -> None:
    body = args.get("request", args)
    root = data_root(value)
    if isinstance(root, dict) and (root.get("error") or root.get("isError")):
        return
    identifier = body.get("identifier", body.get("dataset_id", body.get("id")))
    if isinstance(root, dict):
        identifier = root.get("id", identifier)
    for query in state["queries"].values():
        for match in query["matches"]:
            if match["connection_id"] == tool.connection["id"] and match[
                "dataset_id"
            ] == body.get("identifier", body.get("dataset_id", body.get("id"))):
                match["schema_inspected"] = True


def observation(state: dict[str, Any], tools: list[Any]) -> dict[str, Any]:
    candidates = matches(state)
    suggestions = []
    for candidate in candidates[:12]:
        for tool in tools:
            if (
                tool.original_name == "get_dataset_info"
                and tool.connection["id"] == candidate["connection_id"]
            ):
                from .contracts import AiRuntimeError
                from .policy import validate_arguments

                arguments = None
                for field in ("identifier", "dataset_id", "id"):
                    body = {field: candidate["dataset_id"]}
                    proposed = (
                        {"request": body}
                        if "request" in tool.schema.get("properties", {})
                        else body
                    )
                    try:
                        validate_arguments(tool.schema, proposed)
                    except AiRuntimeError:
                        continue
                    arguments = proposed
                    break
                suggestions.append(
                    {
                        "tool": tool.name,
                        "dataset_id": candidate["dataset_id"],
                        "arguments": arguments,
                        "note": "Inspect the dataset schema before charting.",
                    }
                )
    if not candidates:
        for query in state["queries"].values():
            arguments = query.get("next_arguments")
            tool = next((t for t in tools if t.name == query.get("tool_name")), None)
            if arguments and tool:
                from .contracts import AiRuntimeError
                from .policy import validate_arguments

                try:
                    validate_arguments(tool.schema, arguments)
                except AiRuntimeError:
                    continue
                suggestions.append(
                    {
                        "tool": tool.name,
                        "arguments": arguments,
                        "note": "No exact match yet; continue with this server page.",
                    }
                )
    return {
        "runtime_discovery": {
            "matches": candidates[:12],
            "ambiguous": len(candidates) > 1,
            "suggested_next_steps": suggestions[:12],
            "note": (
                "Recorded evidence, not permission. Exact table names use "
                "table_name eq filters; broad search also matches SQL. Inspect "
                "the matching schema instead of repeating discovery. Clarify "
                "database/schema if matches are ambiguous."
            ),
        }
    }


def intervention(
    state: dict[str, Any], reference: str, tools: list[Any]
) -> dict[str, Any]:
    state["interventions"] += 1
    return {
        "isError": True,
        "code": "discovery_repeated",
        "source": "chat_runtime",
        "external_dispatch": False,
        "evidence_ref": reference,
        "related_evidence_refs": list(
            dict.fromkeys(
                ref
                for query in state["queries"].values()
                for page in query["pages"].values()
                if reference in page.get("evidence_refs", [])
                for ref in page["evidence_refs"]
            )
        )[:32],
        "message": "Not dispatched: this page/range and fields were already requested. "
        "Use recorded evidence, inspect missing schema details, request "
        "a new page/field, or clarify the target.",
        **observation(state, tools),
    }


def read_duplicate(state: dict[str, Any], args: dict[str, Any]) -> str | None:
    identity = key([args["call_id"], args.get("path", [])])
    start = args.get("offset", 0)
    for prior in state["reads"].get(identity, []):
        end = min(start + args.get("limit", 20), prior["total"])
        if prior["request"] == key(args) or (
            prior["start"] <= start and end <= prior["end"]
        ):
            return str(prior["reference"])
    return None


def observe_read(
    state: dict[str, Any], args: dict[str, Any], value: Any, reference: str
) -> None:
    if value.get("isError"):
        return
    identity = key([args["call_id"], args.get("path", [])])
    data = value.get("data")
    length = len(data) if isinstance(data, (str, list, dict)) else 1
    start = value.get("offset", 0)
    state["reads"].setdefault(identity, []).append(
        {
            "request": key(args),
            "start": start,
            "end": start + length,
            "total": value.get("total", start + length),
            "reference": args["call_id"],
            "read_item_ref": reference,
        }
    )

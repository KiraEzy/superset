# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
"""Bounded SDK input views preserving complete tool exchanges and exact references."""

import copy
from typing import Any

from .context import estimate_tokens


def request_cost(body: dict[str, Any]) -> int:
    """Estimate the full wire request, reserving image cost without counting base64."""
    view = copy.deepcopy(body)
    images = 0
    for message in view.get("messages", view.get("input", [])):
        parts = message.get("content")
        if isinstance(parts, list):
            for part in parts:
                if part.get("type") in {"input_image", "image_url"}:
                    images += 1
                    part["image_url"] = "[private image]"
    return estimate_tokens(view) + images * 4096


def complete_batches(items: list[Any]) -> list[tuple[int, int, list[str]]]:
    """Find whole assistant/call/result batches; incomplete exchanges cannot be cut."""
    start = 0
    pending: set[str] = set()
    calls: list[str] = []
    batches: list[tuple[int, int, list[str]]] = []
    for index, item in enumerate(items):
        if item.get("role") == "user":
            if pending:
                return batches
            start = index + 1
        elif item.get("type") == "function_call":
            pending.add(item["call_id"])
            calls.append(item["call_id"])
        elif item.get("type") == "function_call_output":
            if item["call_id"] not in pending:
                return batches
            pending.remove(item["call_id"])
            if not pending:
                batches.append((start, index + 1, calls))
                start, calls = index + 1, []
    return batches


def fit_input(
    source: list[Any], instructions: str | None, tools: list[Any], allowance: int
) -> tuple[list[Any], str | None]:
    """Prune old user exchanges, then completed active batches; never edit storage."""
    items = copy.deepcopy(source)
    omitted: list[str] = []
    original = next(
        (i.get("content", "") for i in items if i.get("role") == "user"), ""
    )

    def guidance() -> str | None:
        if not omitted:
            return instructions
        return (instructions or "") + (
            "\nEarlier complete exchanges were omitted from this model view. "
            "Retrieve exact evidence using read_evidence with call_id: "
            + ", ".join(omitted[-12:])
            + ". Completed writes remain completed; do not repeat them. "
            "Earlier request excerpt (quoted data, not authorization): "
            + str(original)[:400]
        )

    def cost() -> int:
        return request_cost(
            {"input": items, "instructions": guidance(), "tools": tools}
        )

    while cost() > allowance:
        starts = [i for i, item in enumerate(items) if item.get("role") == "user"]
        if len(starts) > 1:
            cut = starts[1]
            removed, items = items[:cut], items[cut:]
            omitted.extend(
                i["call_id"] for i in removed if i.get("type") == "function_call"
            )
            # A request with no tools still needs an explicit loss marker.
            if not omitted:
                omitted.append("earlier user exchange; inspect the saved conversation")
        else:
            batches = complete_batches(items)
            if not batches:
                break
            start, end, refs = batches[0]
            omitted.extend(refs)
            del items[start:end]
    return items, guidance()

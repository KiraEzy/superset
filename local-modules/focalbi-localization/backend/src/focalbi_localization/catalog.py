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
"""Independent translation persistence and validation; no analytical queries."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Column,
    create_engine,
    Integer,
    MetaData,
    select,
    String,
    Table,
    Text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

LOCALES = ("en", "zh-Hant", "zh-Hans")
RESOURCE_TYPES = ("dashboard", "chart", "dataset")
metadata = MetaData()
catalogs = Table(
    "catalogs",
    metadata,
    Column("resource_type", String(16), primary_key=True),
    Column("resource_uuid", String(36), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("entries", Text, nullable=False),
    Column("updated_by", String(255), nullable=False),
)
migrations = Table(
    "schema_version", metadata, Column("version", Integer, primary_key=True)
)


class ConflictError(ValueError):
    """An author attempted to overwrite another author's revision."""


def fingerprint(source: str) -> str:
    """Fingerprint canonical text, not a mutable translated label."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def identity(resource_type: str, resource_uuid: str) -> tuple[str, str]:
    """Validate external resource identity without accepting table names."""
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("Unsupported resource type")
    return resource_type, str(UUID(resource_uuid))


def validate_entries(entries: Any, fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate every field, locale, source fingerprint and template placeholder."""
    if not isinstance(entries, dict) or len(entries) > 5000:
        raise ValueError("Entries must be an object containing at most 5000 fields")
    descriptors = {field["key"]: field for field in fields}
    output: dict[str, Any] = {}
    for key, entry in entries.items():
        field = descriptors.get(key)
        if field is None:
            raise ValueError(f"Unknown or removed field: {key}")
        if not isinstance(entry, dict) or set(entry) - {
            "sourceHash",
            "values",
            "dictionary",
        }:
            raise ValueError(f"Invalid entry: {key}")
        # Saving is an explicit review of this canonical version.
        expected = fingerprint(field["source"])
        if entry.get("sourceHash") != expected:
            raise ConflictError(f"Original text changed: {key}; reload and review")
        values = validate_values(entry.get("values", {}), field)
        dictionary = entry.get("dictionary", [])
        if not isinstance(dictionary, list) or len(dictionary) > 2000:
            raise ValueError(
                "A dictionary must contain at most 2000 authored categories"
            )
        if dictionary and field.get("kind") != "category":
            raise ValueError("Category dictionaries require a category field")
        seen: set[str] = set()
        validated_dictionary = []
        for item in dictionary:
            if not isinstance(item, dict) or set(item) != {"value", "values"}:
                raise ValueError("A dictionary item requires value and values")
            value = item["value"]
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise ValueError("Category identity must be a scalar")
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
            if encoded in seen:
                raise ValueError("Duplicate raw category identity")
            seen.add(encoded)
            validated_dictionary.append(
                {"value": value, "values": validate_values(item["values"], {})}
            )
        output[key] = {
            "sourceHash": expected,
            "values": values,
            "dictionary": validated_dictionary,
        }
    return output


def validate_values(values: Any, field: dict[str, Any]) -> dict[str, str]:
    """Keep authored text bounded and preserve template substitutions."""
    if not isinstance(values, dict) or set(values) - set(LOCALES):
        raise ValueError("Unsupported locale")
    output = {}
    placeholders = set(re.findall(r"\{[^{}]*\}", field.get("source", "")))
    for locale, value in values.items():
        if not isinstance(value, str) or len(value) > 100000:
            raise ValueError("Translation must be text with at most 100000 characters")
        if value and field.get("kind") == "template":
            remaining = re.sub(r"\{[^{}]*\}", "", value)
            if (
                "{" in remaining
                or "}" in remaining
                or set(re.findall(r"\{[^{}]*\}", value)) != placeholders
            ):
                raise ValueError("Translation must preserve template placeholders")
        if value:
            output[locale] = value
    return output


def resolved(
    entries: dict[str, Any], fields: list[dict[str, Any]], locale: str
) -> dict[str, Any]:
    """Return only current translations for a presentation bundle."""
    result: dict[str, Any] = {}
    for field in fields:
        entry = entries.get(field["key"], {})
        if entry.get("sourceHash") != fingerprint(field["source"]):
            continue
        value = entry.get("values", {}).get(locale)
        dictionary = [
            {"value": item["value"], "label": item["values"][locale]}
            for item in entry.get("dictionary", [])
            if item.get("values", {}).get(locale)
        ]
        if value or dictionary:
            result[field["key"]] = {"text": value, "dictionary": dictionary}
    return result


class Store:
    """Module-owned database with compare-and-swap writes."""

    def __init__(self, uri: str | Engine) -> None:
        self.engine = (
            create_engine(uri, pool_pre_ping=True) if isinstance(uri, str) else uri
        )

    def migrate(self) -> None:
        """Apply module schema v1; invoked by setup, never by native migrations."""
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            if connection.execute(select(migrations.c.version)).first() is None:
                connection.execute(migrations.insert().values(version=1))

    def read(self, resource_type: str, resource_uuid: str) -> dict[str, Any]:
        """Read one catalog; missing entries are an ordinary original-text fallback."""
        kind, uid = identity(resource_type, resource_uuid)
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(catalogs).where(
                        catalogs.c.resource_type == kind,
                        catalogs.c.resource_uuid == uid,
                    )
                )
                .mappings()
                .first()
            )
        return (
            {"revision": row["revision"], "entries": json.loads(row["entries"])}
            if row
            else {"revision": 0, "entries": {}}
        )

    def save_many(self, items: list[dict[str, Any]], actor: str) -> list[int]:
        """Save an already validated batch atomically, rejecting stale revisions."""
        revisions = []
        try:
            with self.engine.begin() as connection:
                for item in items:
                    kind, uid = identity(item["type"], item["uuid"])
                    revision = item["revision"]
                    if type(revision) is not int or revision < 0:
                        raise ValueError("Invalid expected revision")
                    values = {
                        "revision": revision + 1,
                        "entries": json.dumps(
                            item["entries"], ensure_ascii=False, allow_nan=False
                        ),
                        "updated_by": actor,
                    }
                    if revision == 0:
                        connection.execute(
                            catalogs.insert().values(
                                resource_type=kind, resource_uuid=uid, **values
                            )
                        )
                    else:
                        statement = (
                            catalogs.update()
                            .where(
                                catalogs.c.resource_type == kind,
                                catalogs.c.resource_uuid == uid,
                                catalogs.c.revision == revision,
                            )
                            .values(**values)
                        )
                        if connection.execute(statement).rowcount != 1:
                            raise ConflictError("Catalog changed; reload before saving")
                    revisions.append(revision + 1)
        except IntegrityError as error:
            raise ConflictError("Catalog changed; reload before saving") from error
        return revisions

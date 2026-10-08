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
"""Meaningful catalog behavior independent of any business dataset."""

import sys
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
if Path("/app/focalbi-localization/extension/dist/backend/src").exists():
    sys.path.insert(0, "/app/focalbi-localization/extension/dist/backend/src")
from focalbi_localization.catalog import (
    ConflictError,
    fingerprint,
    resolved,
    Store,
    validate_entries,
)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store("sqlite://")
        self.store.migrate()
        self.uid = str(uuid4())
        self.fields = [
            {"key": "title", "source": "{selection} population", "kind": "template"},
            {"key": "region", "source": "region_code", "kind": "category"},
        ]

    def entry(self, source: str, **values: str) -> dict:
        return {"sourceHash": fingerprint(source), "values": values, "dictionary": []}

    def tearDown(self) -> None:
        self.store.engine.dispose()

    def test_missing_and_changed_text_fall_back_without_cross_script_fallback(
        self,
    ) -> None:
        entries = {
            "title": self.entry(
                "{selection} population", **{"zh-Hant": "{selection}人口"}
            )
        }
        self.assertEqual(resolved(entries, self.fields, "zh-Hans"), {})
        self.fields[0]["source"] = "{selection} income"
        self.assertEqual(resolved(entries, self.fields, "zh-Hant"), {})

    def test_placeholder_and_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_entries(
                {"title": self.entry("{selection} population", **{"zh-Hant": "人口"})},
                self.fields,
            )
        with self.assertRaises(ValueError):
            validate_entries({"other": self.entry("label", en="changed")}, self.fields)

    def test_dictionary_keeps_distinct_raw_values_with_same_display_label(self) -> None:
        entry = self.entry("region_code")
        entry["dictionary"] = [
            {"value": raw, "values": {"zh-Hant": "地區"}} for raw in ("N", "S")
        ]
        valid = validate_entries({"region": entry}, self.fields)
        self.assertEqual(
            [
                item["value"]
                for item in resolved(valid, self.fields, "zh-Hant")["region"][
                    "dictionary"
                ]
            ],
            ["N", "S"],
        )
        entry["dictionary"].append(entry["dictionary"][0])
        with self.assertRaises(ValueError):
            validate_entries({"region": entry}, self.fields)

    def test_revision_conflict_and_batch_rollback(self) -> None:
        item = {"type": "dashboard", "uuid": self.uid, "revision": 0, "entries": {}}
        self.assertEqual(self.store.save_many([item], "author"), [1])
        other_uid = str(uuid4())
        with self.assertRaises(ConflictError):
            self.store.save_many([{**item, "uuid": other_uid}, item], "second-author")
        self.assertEqual(self.store.read("dashboard", other_uid)["revision"], 0)
        self.assertEqual(self.store.read("dashboard", self.uid)["revision"], 1)

    def test_original_change_requires_explicit_review(self) -> None:
        with self.assertRaises(ConflictError):
            validate_entries(
                {"title": self.entry("Old label", en="Translation")}, self.fields
            )

    def test_forbidden_resource_type_and_non_scalar_dictionary(self) -> None:
        with self.assertRaises(ValueError):
            self.store.read("sql", self.uid)
        entry = self.entry("region_code")
        entry["dictionary"] = [{"value": {"sql": "select"}, "values": {"en": "unsafe"}}]
        with self.assertRaises(ValueError):
            validate_entries({"region": entry}, self.fields)


if __name__ == "__main__":
    unittest.main()

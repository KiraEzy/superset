# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Test source semantics and the prepared release independently of Superset."""

from __future__ import annotations

import csv
import hashlib
import json  # noqa: TID251 -- Tests do not import the Superset runtime.
import unittest
from decimal import Decimal, InvalidOperation

from prepare import measure_metadata, parse_value, ROOT, specifications, validate_cells

# Standard-library unittest keeps validation runnable without Superset.
# ruff: noqa: PT009, PT027


class CensusContracts(unittest.TestCase):
    """Keep nil, unavailable, reference totals and medians distinguishable."""

    def test_published_symbols(self) -> None:
        """A published nil is not a missing or not-applicable observation."""
        self.assertEqual(parse_value("-"), (Decimal(0), "published_nil"))
        self.assertEqual(parse_value(".."), (None, "not_applicable"))
        self.assertEqual(parse_value("N.A."), (None, "not_available"))
        self.assertEqual(parse_value("0.0"), (Decimal("0.0"), "published"))
        with self.assertRaises(InvalidOperation):
            parse_value("unexpected source symbol")

    def test_income_count_is_households_not_currency(self) -> None:
        """Income bands count households; a median income measures HKD."""
        self.assertEqual(
            measure_metadata(
                "Domestic households by monthly domestic household income (HK$)"
            ),
            ("count", "households"),
        )
        self.assertEqual(
            measure_metadata("Median monthly income (HK$)"), ("median", "HKD")
        )
        self.assertEqual(
            measure_metadata("Median rent to income ratio"), ("median", "percent")
        )

    def test_native_resource_contract(self) -> None:
        """Queries exclude references and retain distinct statistical populations."""
        spec = specifications("test-release")
        with self.assertRaises(ValueError):
            specifications("release' OR 1=1 --")
        self.assertEqual(len(spec["charts"]), 31)
        self.assertEqual(len(spec["datasets"]), 23)
        self.assertEqual(len(spec["tabs"]), 6)
        datasets = {item["key"]: item for item in spec["datasets"]}
        charts = {item["key"]: item for item in spec["charts"]}
        for item in datasets.values():
            self.assertIn("g.geography_kind = 'district'", item["sql"])
            self.assertNotIn("AVG(", item["sql"])
        self.assertIn(
            "MAX(CASE WHEN c.indicator_code = 'ma_hh'", datasets["summary"]["sql"]
        )
        self.assertNotIn("SUM(", datasets["summary"]["sql"])
        self.assertEqual(
            charts["elderly"]["config"]["metric"],
            {
                "name": "elderly_population",
                "aggregate": "SUM",
                "ratio_denominator": "population",
                "label": "Population aged 65+ share",
            },
        )
        self.assertEqual(charts["source"]["config"]["row_limit"], 10000)
        for key in ["district_table", "housing_table", "source"]:
            sort_by = charts[key]["config"]["sort_by"]
            assert isinstance(sort_by, list)
            for value in sort_by:
                column, ascending = json.loads(value)
                self.assertIsInstance(column, str)
                self.assertIs(ascending, True)
        self.assertIn("mearn_xfdhfw_1", datasets["employment_income"]["sql"])

    @unittest.skipUnless(
        (ROOT / "snapshot/hk_census_2021_cell.csv").exists(), "Run prepare.py first"
    )
    def test_official_snapshot_and_reject_corruption(self) -> None:
        """Reviewed totals reconcile; duplicate or altered cells are rejected."""
        provenance = json.loads((ROOT / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256((ROOT / "snapshot/DC_21C.CSV").read_bytes()).hexdigest(),
            provenance["release"]["csv_sha256"],
        )
        with (ROOT / "snapshot/hk_census_2021_geography.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            geographies = list(csv.DictReader(stream))
        with (ROOT / "snapshot/hk_census_2021_cell.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            cells = list(csv.DictReader(stream))
        result = validate_cells(geographies, cells)
        self.assertEqual(result["totals"]["t_pop"], 7411945)
        self.assertEqual(result["totals"]["dh"], 2673714)
        self.assertEqual(result["totals"]["age_5"], 1451444)
        self.assertFalse(
            provenance["whole_hong_kong_reference"]["used_in_district_aggregation"]
        )
        with self.assertRaises(ValueError):
            validate_cells(geographies, cells + [cells[0]])
        corrupted = [dict(row) for row in cells]
        corrupted[0]["numeric_value"] = "1"
        with self.assertRaises(ValueError):
            validate_cells(geographies, corrupted)


if __name__ == "__main__":
    unittest.main()

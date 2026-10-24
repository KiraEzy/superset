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
"""Prepare official A204 joint age/sex counts, validating against the district profile."""

import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "https://www.censtatd.gov.hk/en/data/stat_report/product/D5212101/att/D5212101E2021XXXXE.zip"


def prepare() -> dict[str, object]:
    """Extract five-year bands from single ages; reject changed source contracts."""
    snapshot = ROOT / "snapshot"
    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.censtatd.gov.hk/en/scode470.html",
        },
    )
    archive = urllib.request.urlopen(request, timeout=60).read()
    source = zipfile.ZipFile(io.BytesIO(archive)).read("Table A204.csv")
    table = list(csv.reader(io.StringIO(source.decode("utf-8-sig"))))
    assert table[0][0] == "Table A204 : Population by Sex, Age, Year and District Council District"
    assert table[4][2:] == ["2021"] * 19
    assert table[5][-1] == "Land"
    with (snapshot / "hk_census_2021_geography.csv").open(encoding="utf-8-sig") as stream:
        geos = {r["district_name"]: r for r in csv.DictReader(stream) if r["geography_kind"] == "district"}
    names = [name.removesuffix(" (1)") for name in table[5][2:-1]]
    assert len(names) == 18 and set(names) == set(geos)
    with (snapshot / "hk_census_2021_cell.csv").open(encoding="utf-8-sig") as stream:
        cells = {(r["district_code"], r["indicator_code"]): int(float(r["numeric_value"]))
                 for r in csv.DictReader(stream) if r["indicator_code"] in
                 ["t_pop", "pop_m", "pop_f", "age_1", "age_2", "age_3", "age_4", "age_5"]}
    bands = defaultdict(int)
    broad = defaultdict(int)
    sexes = defaultdict(int)
    seen = set()
    for row in table[7:]:
        if row[0] not in {"Male", "Female"} or not (row[1].isdigit() or row[1] == "85+"):
            continue
        sex, age = row[0], int(row[1].removesuffix("+"))
        assert 0 <= age <= 85
        assert (sex, age) not in seen
        seen.add((sex, age))
        assert all(v.isdigit() for v in row[2:])
        counts = [int(v) for v in row[2:]]
        assert sum(counts[:-1]) == counts[-1]
        for name, count in zip(names, counts[:-1], strict=True):
            bands[name, sex, age // 5 * 5] += count
            sexes[name, sex] += count
            age_group = 1 if age < 15 else 2 if age < 25 else 3 if age < 45 else 4 if age < 65 else 5
            broad[name, age_group] += count
    assert len(seen) == 172 and len(bands) == 648
    for name, geo in geos.items():
        code = geo["district_code"]
        for sex, indicator in [("Male", "pop_m"), ("Female", "pop_f")]:
            assert sexes[name, sex] == cells[code, indicator]
        assert sexes[name, "Male"] + sexes[name, "Female"] == cells[code, "t_pop"]
        for age_group in range(1, 6):
            assert broad[name, age_group] == cells[code, f"age_{age_group}"]
    output = []
    for (name, sex, lower), count in sorted(bands.items()):
        geo = geos[name]
        output.append({
            "district_code": geo["district_code"], "district_name": name,
            "region": geo["region"], "census_year": 2021,
            "age_lower": lower, "age_band": f"{lower:02d}-{lower + 4:02d}" if lower < 85 else "85+",
            "sex": sex, "count_value": count,
            "signed_count": -count if sex == "Male" else count,
            "district_population": cells[geo["district_code"], "t_pop"],
        })
    assert sum(r["count_value"] for r in output) == 7411945
    with (snapshot / "hk_census_2021_age_sex.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    (snapshot / "demographic-tables.zip").write_bytes(archive)
    (snapshot / "A204.csv").write_bytes(source)
    provenance = {
        "source_url": URL, "table": "A204", "source_release_date": "2022-05-31",
        "reference_year": 2021, "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "csv_sha256": hashlib.sha256(source).hexdigest(), "rows": 648,
        "coverage": "18 land districts, all residents including foreign domestic helpers; excludes Marine and Land reference",
        "transformation": "Sum single ages 0-84 into five-year bands; retain published 85+ top code. No age-by-sex estimation.",
        "validation": "Each district's male/female counts and five broad age-band counts exactly match reviewed DC_21C.CSV.",
        "population": 7411945,
        "maximum_district_sex_age_share": max(r["count_value"] / r["district_population"] for r in output),
    }
    (ROOT / "pyramid-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))

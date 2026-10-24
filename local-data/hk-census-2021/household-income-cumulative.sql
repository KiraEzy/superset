-- Licensed to the Apache Software Foundation (ASF) under one
-- or more contributor license agreements. See the NOTICE file
-- distributed with this work for additional information
-- regarding copyright ownership. The ASF licenses this file
-- to you under the Apache License, Version 2.0 (the
-- "License"); you may not use this file except in compliance
-- with the License. You may obtain a copy of the License at
--
--   http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing,
-- software distributed under the License is distributed on an
-- "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
-- KIND, either express or implied. See the License for the
-- specific language governing permissions and limitations
-- under the License.

WITH district_bands AS (
 SELECT g.district_code,g.district_name,g.region,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dh') AS household_count,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_1') AS income_1,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_2') AS income_2,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_3') AS income_3,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_4') AS income_4,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_5') AS income_5,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_6') AS income_6,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='dhi_7') AS income_7
 FROM public.hk_census_2021_cell c JOIN public.hk_census_2021_geography g USING(district_code)
 WHERE c.release_id='dc2021-f099e9b34408' AND c.census_year=2021
 AND g.geography_kind='district' AND c.indicator_code IN ('dh','dhi_1','dhi_2','dhi_3','dhi_4','dhi_5','dhi_6','dhi_7')
 GROUP BY g.district_code,g.district_name,g.region
), thresholds(income_threshold,band_number) AS (VALUES (6000,1),(10000,2),(20000,3),(30000,4),(40000,5),(60000,6))
SELECT d.district_code,d.district_name,d.region,t.income_threshold,d.household_count,
 CASE WHEN t.band_number>=1 THEN d.income_1 ELSE 0 END + CASE WHEN t.band_number>=2 THEN d.income_2 ELSE 0 END + CASE WHEN t.band_number>=3 THEN d.income_3 ELSE 0 END + CASE WHEN t.band_number>=4 THEN d.income_4 ELSE 0 END + CASE WHEN t.band_number>=5 THEN d.income_5 ELSE 0 END + CASE WHEN t.band_number>=6 THEN d.income_6 ELSE 0 END AS households_below_threshold
FROM district_bands d CROSS JOIN thresholds t

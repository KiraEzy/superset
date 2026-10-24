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

WITH medians AS (
 SELECT g.district_code,g.district_name,g.district_name_zh,g.region,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='ma_hh') AS all_households_median,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='ma_econhh') AS active_households_median
 FROM public.hk_census_2021_cell c JOIN public.hk_census_2021_geography g USING(district_code)
 WHERE c.release_id='dc2021-f099e9b34408' AND c.census_year=2021
 AND g.geography_kind='district' AND c.indicator_code IN ('ma_hh','ma_econhh')
 GROUP BY g.district_code,g.district_name,g.district_name_zh,g.region
)
SELECT *, active_households_median-all_households_median AS median_difference,
 all_households_median/700 AS all_position,active_households_median/700 AS active_position,
 (active_households_median-all_households_median)/700 AS gap_width,
 ROW_NUMBER() OVER (ORDER BY active_households_median-all_households_median DESC,district_name) AS display_order
FROM medians

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

-- Both measures cover all domestic households, not only economically active ones.
WITH district_income AS (
    SELECT g.district_code, g.district_name, g.district_name_zh, g.region,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dh') AS household_count,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'ma_hh') AS median_income_hkd,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_1') AS income_1,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_2') AS income_2,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_3') AS income_3,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_4') AS income_4,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_5') AS income_5,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_6') AS income_6,
        MAX(c.numeric_value) FILTER (WHERE c.indicator_code = 'dhi_7') AS income_7
    FROM public.hk_census_2021_cell c
    JOIN public.hk_census_2021_geography g ON g.district_code = c.district_code
    WHERE c.release_id = 'dc2021-f099e9b34408'
        AND c.census_year = 2021 AND g.geography_kind = 'district'
        AND c.indicator_code IN ('dh', 'ma_hh', 'dhi_1', 'dhi_2', 'dhi_3', 'dhi_4', 'dhi_5', 'dhi_6', 'dhi_7')
    GROUP BY g.district_code, g.district_name, g.district_name_zh, g.region
)
SELECT *,
    ROW_NUMBER() OVER (ORDER BY median_income_hkd DESC, district_code) AS display_order,
    100.0 * income_1 / NULLIF(household_count, 0) AS share_1,
    100.0 * income_2 / NULLIF(household_count, 0) AS share_2,
    100.0 * income_3 / NULLIF(household_count, 0) AS share_3,
    100.0 * income_4 / NULLIF(household_count, 0) AS share_4,
    100.0 * income_5 / NULLIF(household_count, 0) AS share_5,
    100.0 * income_6 / NULLIF(household_count, 0) AS share_6,
    100.0 * income_7 / NULLIF(household_count, 0) AS share_7,
    100.0 * median_income_hkd / 60000.0 AS median_position
FROM district_income

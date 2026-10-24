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

-- Separate district aggregates, not an individual-level joint distribution.
WITH district_counts AS (
    SELECT
        g.district_code,
        g.district_name,
        g.district_name_zh,
        g.region,
        MAX(CASE WHEN c.indicator_code = 't_pop' THEN c.numeric_value END) AS population,
        MAX(CASE WHEN c.indicator_code = 'born_else' THEN c.numeric_value END) AS born_elsewhere_count,
        MAX(CASE WHEN c.indicator_code = 'ul_eng' THEN c.numeric_value END) AS english_count,
        SUM(CASE WHEN c.indicator_code IN ('ul_can', 'ul_put', 'ul_othchi', 'ul_eng', 'ul_oth')
            THEN c.numeric_value ELSE 0 END) AS language_population
    FROM public.hk_census_2021_cell AS c
    JOIN public.hk_census_2021_geography AS g ON g.district_code = c.district_code
    WHERE c.release_id = 'dc2021-f099e9b34408'
        AND c.census_year = 2021
        AND g.geography_kind = 'district'
        AND c.indicator_code IN ('t_pop', 'born_else', 'ul_can', 'ul_put', 'ul_othchi', 'ul_eng', 'ul_oth')
    GROUP BY g.district_code, g.district_name, g.district_name_zh, g.region
)
SELECT *,
    district_name || ' / ' || district_name_zh AS district_label,
    CASE region
        WHEN 'Hong Kong Island' THEN 'Hong Kong Island / 香港島'
        WHEN 'Kowloon' THEN 'Kowloon / 九龍'
        WHEN 'New Territories' THEN 'New Territories / 新界'
    END AS region_label,
    born_elsewhere_count / NULLIF(population, 0) AS born_elsewhere_share,
    english_count / NULLIF(language_population, 0) AS english_share
FROM district_counts

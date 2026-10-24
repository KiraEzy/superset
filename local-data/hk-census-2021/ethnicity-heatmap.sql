-- Licensed to the Apache Software Foundation (ASF) under one or more
-- contributor license agreements. See the NOTICE file distributed with
-- this work for additional information regarding copyright ownership.
-- The ASF licenses this file to You under the Apache License, Version 2.0
-- (the "License"); you may not use this file except in compliance with
-- the License. You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

WITH counts AS (
    SELECT g.district_code, g.district_name, g.district_name_zh, g.region,
        MAX(CASE WHEN c.indicator_code = 't_pop' THEN c.numeric_value END) AS population,
        MAX(CASE WHEN c.indicator_code = 'ethn_chi' THEN c.numeric_value END) AS chinese_count,
        MAX(CASE WHEN c.indicator_code = 'ethn_phi' THEN c.numeric_value END) AS filipino_count,
        MAX(CASE WHEN c.indicator_code = 'ethn_ind' THEN c.numeric_value END) AS indonesian_count,
        MAX(CASE WHEN c.indicator_code = 'ethn_wh' THEN c.numeric_value END) AS white_count,
        MAX(CASE WHEN c.indicator_code = 'ethn_oth' THEN c.numeric_value END) AS others_count
    FROM public.hk_census_2021_cell c
    JOIN public.hk_census_2021_geography g ON g.district_code = c.district_code
    WHERE c.release_id = 'dc2021-f099e9b34408' AND c.census_year = 2021
        AND g.geography_kind = 'district'
        AND c.indicator_code IN ('t_pop','ethn_chi','ethn_phi','ethn_ind','ethn_wh','ethn_oth')
    GROUP BY g.district_code, g.district_name, g.district_name_zh, g.region
), shares AS (
    SELECT *, (population - chinese_count) / NULLIF(population, 0) AS non_chinese_share,
        filipino_count / NULLIF(population, 0) AS filipino_share,
        indonesian_count / NULLIF(population, 0) AS indonesian_share,
        white_count / NULLIF(population, 0) AS white_share,
        others_count / NULLIF(population, 0) AS others_share
    FROM counts
)
SELECT *,
    TO_CHAR(filipino_count, 'FM999,999,999') AS filipino_count_label,
    TO_CHAR(100 * filipino_share, 'FM990.00') || '%' AS filipino_share_label,
    'rgb(' || ROUND(247 - 171 * LEAST(filipino_share / 0.12, 1))::text || ',' || ROUND(251 - 105 * LEAST(filipino_share / 0.12, 1))::text || ',' || ROUND(255 - 60 * LEAST(filipino_share / 0.12, 1))::text || ')' AS filipino_color,
    TO_CHAR(indonesian_count, 'FM999,999,999') AS indonesian_count_label,
    TO_CHAR(100 * indonesian_share, 'FM990.00') || '%' AS indonesian_share_label,
    'rgb(' || ROUND(247 - 171 * LEAST(indonesian_share / 0.12, 1))::text || ',' || ROUND(251 - 105 * LEAST(indonesian_share / 0.12, 1))::text || ',' || ROUND(255 - 60 * LEAST(indonesian_share / 0.12, 1))::text || ')' AS indonesian_color,
    TO_CHAR(white_count, 'FM999,999,999') AS white_count_label,
    TO_CHAR(100 * white_share, 'FM990.00') || '%' AS white_share_label,
    'rgb(' || ROUND(247 - 171 * LEAST(white_share / 0.12, 1))::text || ',' || ROUND(251 - 105 * LEAST(white_share / 0.12, 1))::text || ',' || ROUND(255 - 60 * LEAST(white_share / 0.12, 1))::text || ')' AS white_color,
    TO_CHAR(others_count, 'FM999,999,999') AS others_count_label,
    TO_CHAR(100 * others_share, 'FM990.00') || '%' AS others_share_label,
    'rgb(' || ROUND(247 - 171 * LEAST(others_share / 0.12, 1))::text || ',' || ROUND(251 - 105 * LEAST(others_share / 0.12, 1))::text || ',' || ROUND(255 - 60 * LEAST(others_share / 0.12, 1))::text || ')' AS others_color
FROM shares
ORDER BY district_name

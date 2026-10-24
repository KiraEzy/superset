-- District aggregates describe an association, not individual education-to-job paths.
WITH counts AS (
 SELECT g.district_code,g.district_name,g.district_name_zh,g.region,
 SUM(c.numeric_value) FILTER (WHERE c.indicator_code IN ('edu_prepri','edu_pri','edu_lsed','edu_usec','edu_dip','edu_sub','edu_deg')) AS population_15_plus,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='edu_deg') AS degree_course_population,
 SUM(c.numeric_value) FILTER (WHERE c.indicator_code IN ('wp_a','wp_b','wp_c')) AS managerial_professional_population,
 SUM(c.numeric_value) FILTER (WHERE c.indicator_code IN ('wp_a','wp_b','wp_c','wp_d','wp_e','wp_f','wp_g','wp_h','wp_i')) AS working_population
 FROM public.hk_census_2021_cell c JOIN public.hk_census_2021_geography g USING(district_code)
 WHERE c.release_id='dc2021-f099e9b34408' AND c.census_year=2021 AND g.geography_kind='district'
 AND c.indicator_code IN ('edu_prepri','edu_pri','edu_lsed','edu_usec','edu_dip','edu_sub','edu_deg','wp_a','wp_b','wp_c','wp_d','wp_e','wp_f','wp_g','wp_h','wp_i')
 GROUP BY g.district_code,g.district_name,g.district_name_zh,g.region
)
SELECT *,degree_course_population/NULLIF(population_15_plus,0) AS degree_course_share,
 managerial_professional_population/NULLIF(working_population,0) AS managerial_professional_share,
 district_name || ' / ' || district_name_zh AS district_label,
 CASE region WHEN 'Hong Kong Island' THEN 'Hong Kong Island / 香港島' WHEN 'Kowloon' THEN 'Kowloon / 九龍' ELSE 'New Territories / 新界' END AS region_label
FROM counts

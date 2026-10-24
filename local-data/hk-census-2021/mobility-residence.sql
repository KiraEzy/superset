-- Seven exhaustive published counts, grouped into four residence-change statuses.
WITH statuses AS (
 SELECT g.district_code,g.district_name,g.region,
 CASE WHEN c.indicator_code IN ('pm_hk','pm_kln','pm_nt','pm_oth') THEN 'Internally migrated'
 WHEN c.indicator_code='pm_samearea' THEN 'Moved within same area'
 WHEN c.indicator_code='pm_same' THEN 'Remained at same address'
 ELSE 'Previously outside Hong Kong' END AS residence_status,
 SUM(c.numeric_value) AS persons
 FROM public.hk_census_2021_cell c JOIN public.hk_census_2021_geography g USING(district_code)
 WHERE c.release_id='dc2021-f099e9b34408' AND g.geography_kind='district'
 AND c.indicator_code IN ('pm_hk','pm_kln','pm_nt','pm_oth','pm_samearea','pm_same','pm_out')
 GROUP BY g.district_code,g.district_name,g.region,residence_status
)
SELECT *,SUM(persons) OVER(PARTITION BY district_code) AS population_5_plus,
 persons/NULLIF(SUM(persons) OVER(PARTITION BY district_code),0) AS residence_share
FROM statuses

-- Each district is one observation; these are separate worker/student populations.
WITH counts AS (
 SELECT g.district_code,g.district_name,g.region,
 SUM(c.numeric_value) FILTER (WHERE c.indicator_code LIKE 'plw_%') AS workers,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='plw_same') AS local_workers,
 SUM(c.numeric_value) FILTER (WHERE c.indicator_code IN ('pls_same','pls_diff_hk','pls_diff_kln','pls_diff_nt','s_diff_oth')) AS students,
 MAX(c.numeric_value) FILTER (WHERE c.indicator_code='pls_same') AS local_students
 FROM public.hk_census_2021_cell c JOIN public.hk_census_2021_geography g USING(district_code)
 WHERE c.release_id='dc2021-f099e9b34408' AND g.geography_kind='district'
 AND (c.indicator_code LIKE 'plw_%' OR c.indicator_code IN ('pls_same','pls_diff_hk','pls_diff_kln','pls_diff_nt','s_diff_oth'))
 GROUP BY g.district_code,g.district_name,g.region
)
SELECT *,local_workers/NULLIF(workers,0) AS local_work_share,
 local_students/NULLIF(students,0) AS local_study_share FROM counts

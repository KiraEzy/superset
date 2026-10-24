SELECT g.district_code,g.district_name,g.region,c.census_year,
 CASE WHEN c.indicator_code IN ('dh_ocm','dh_ocwm') THEN 'Owner-occupied'
      WHEN c.indicator_code IN ('dh_st','dh_co') THEN 'Rented' ELSE 'Other arrangements' END AS tenure_group,
 CASE c.indicator_code WHEN 'dh_ocm' THEN 'With mortgage or loan'
 WHEN 'dh_ocwm' THEN 'Without mortgage or loan' WHEN 'dh_st' THEN 'Sole tenant'
 WHEN 'dh_co' THEN 'Shared tenancy' WHEN 'dh_rf' THEN 'Rent free'
 WHEN 'dh_emp' THEN 'Employer provided' END AS tenure_type,
 i.category_en AS source_category,c.numeric_value AS household_count,
 c.indicator_code,i.footnotes,i.universe
FROM public.hk_census_2021_cell c
JOIN public.hk_census_2021_geography g USING(district_code)
JOIN public.hk_census_2021_indicator i USING(indicator_code)
WHERE c.release_id='dc2021-f099e9b34408' AND c.census_year=2021
AND g.geography_kind='district'
AND c.indicator_code IN ('dh_ocm','dh_ocwm','dh_st','dh_co','dh_rf','dh_emp')

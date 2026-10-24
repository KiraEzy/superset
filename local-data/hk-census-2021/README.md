# Hong Kong Census 2021 workflow

This workflow prepares official **published district aggregates** and creates a
native Superset dashboard. It introduces no Superset, MCP or renderer features.
Dashboard 18 is **Hong Kong Census 2021 - People, Households and Districts**;
its UUID, charts and datasets are recorded in [resources.json](./resources.json).
Open the [published LAN dashboard](http://192.168.10.27:8088/superset/dashboard/18/)
with your Superset login. Publication does not grant anonymous access.

## Website embedding

Dashboard 18 is enabled for embedding from `http://192.168.10.27:3040`.
Its embedding UUID is `1574273e-62ca-4082-94dd-fd7b013831a8` (distinct
from the dashboard UUID). The approved website audience may view all published
census rows without login or row restrictions. The native dashboard URL still
requires a Superset login; website guests use short-lived tokens.

Use the existing EmbeddedViewer role and token configuration described in the
[embedding guide](../../docs/admin_docs/configuration/focalbi-embedding.mdx).
The website backend must issue a token with only this embedding UUID as its
dashboard resource and an empty `rls_rules` list when signing directly. Existing
HS256 signing, audience `focalbi-embedded`, and 300-second expiry apply. Keep the
signing secret server-side. The SDK browser URL is `http://192.168.10.27:8088`.
The website integrates this binding on [OPEN.GOV](http://192.168.10.27:3040/en/p/open-gov)
through its separate `/api/focalbi/census/config` and
`/api/focalbi/census/guest-token` endpoints.

To verify provider configuration, the embedded route must return 200 with this
website's Referer and 403 with an unapproved origin. A census-scoped guest token
must read dashboard 18 and its chart definitions, and must not read dashboard 16.
Complete browser rendering, filter, chart-query and token-renewal checks on the
host website after integration.

## Source and tables

The source is the Census and Statistics Department's
[2021 population and household district profile](https://data.gov.hk/en-data/dataset/hk-censtatd-census21c-d5212109).
The reviewed resource was updated on 27 April 2026; the reference year remains
2021. `prepare.py` downloads the official multi-geography archive and reads only
`DC_21C.CSV`. Source hashes, symbols and benchmarks are in
[provenance.json](./provenance.json).

Five physical tables reside in database 1, schema `public`:

| Table | Grain |
| --- | --- |
| `hk_census_2021_release` | One reviewed source release |
| `hk_census_2021_geography` | 18 districts and one separate Land reference |
| `hk_census_2021_indicator` | 205 source fields, bilingual labels, units and notes |
| `hk_census_2021_cell` | Release × geography × indicator; 3,895 published cells |
| `hk_census_2021_age_sex` | District × sex × five-year age band; 648 A204 cells |

The 34 analytical virtual datasets select only the 18 land districts; 26 are used
by the dashboard, while the original age, language, ethnicity, income, tenure,
occupation, study-place and migration-status distributions remain available. The source
table chart contains **3,690 cells**, not individual census respondents. The
summary dataset has one row per district. Each distribution dataset represents
one statistical population; it does not manufacture age × ethnicity × income
cross-tabulations from unrelated marginal totals.

## Page layouts and district map

[presentation.json](./presentation.json) records the MCP/native chart overrides, six page
layouts (12-column widths and native height units), map settings and boundary
provenance. Apply these after the baseline `prepare.py` specifications. Overview
has four headline figures, an eight-column map, a population pyramid and comparison
table. The other pages pair related charts using columns, stacked bars, donuts,
horizontal rankings and tables. Methodology is at the end of Mobility and sources.
The full-width district ranking in People and diversity (chart 149) shows
**elderly dependency ratio**. The saved summary-dataset metric is
`1000 * SUM(elderly_population) / NULLIF(SUM(population) - SUM(children_population) - SUM(elderly_population), 0)`.
This is residents aged 65+ per 1,000 residents aged 15–64, following the
[2021 Census definition](https://www.census2021.gov.hk/doc/pub/21c-main-results.pdf).
The denominator is the age group, not employed persons; the ratio does not measure
actual employment, care needs or financial dependence. District values are ranked
highest first with one decimal place and a fixed 0–400 scale. The original chart
ID, dataset 31, map, native filter scopes and cache policy are retained.
Provision `dataset_metric_overrides.summary` from `presentation.json` through the
native dataset API before applying chart 149's MCP override. Preserve existing
dataset metrics when adding this saved metric; MCP cannot author dataset metrics.
Verify 18 district values, Eastern 349.1 and Islands 203.4, and that selecting those
two districts leaves their ratios unchanged. Check the title, metric and axis
labels in English and both Chinese locales.

Population by sex uses a full pie with percentage labels and a legend; its centre
total label is disabled. This saved MCP override is included in `presentation.json`.
Population pyramid by age and sex replaces the five-band age chart (151). Official
joint age/sex counts from table A204 supply 18 five-year bands, ending with the
published 85+ category. Males extend left, females right, with youngest ages at
the bottom. Each bar is `SUM(signed_count) / SUM(district_population)`, grouped by
age band and sex. Exactly one row per district/age/sex makes that denominator the
selected districts' total population, not the population of one sex. Negative
male coordinates only control direction; `count_value` remains positive. Symmetric
−7% to +7% axes remain comparable under filters and cover every district's largest
age/sex share (6.77%). The chart note explains direction and coverage. This is an
MCP horizontal stacked-bar configuration with native axis bounds in a four-column,
60-unit card beside the map on Overview. Its explanatory note follows that row.
Chart 149 occupies the pyramid's former full-width, 72-unit slot in People and
diversity. Chart component IDs and native filter scopes survive the swap.
Titles, age bands, legend, axes and note support both Chinese locales.
The population includes foreign domestic helpers and excludes Marine; the Land
reference is used for validation only. [pyramid-provenance.json](./pyramid-provenance.json)
records official archive/CSV hashes and reconciliation to the district profile.

Population by birthplace uses a full-width native treemap (`treemap_v2`): birthplace
group → district of residence in 2021, sized by `SUM(count_value)`. Its three groups
contain 54 district leaves and reconcile to 7,411,945 persons. Districts identify
residence, not district of birth. Hover reveals full labels, counts and share of
the parent group. Region/District filters retain their native scope. The installed
MCP cannot save treemaps; use its chart-data tools for validation and apply this
chart's `native_chart_overrides` through native Explore/API. Its saved chart ID,
dataset and cache policy remain unchanged. Internal treemap labels/tooltips are
English; the chart title follows the content locale.
The chart's optional `focalbi_treemap_group_colors` setting assigns blue to Hong
Kong, green to Mainland China/Macao/Taiwan, and amber to Elsewhere. District tiles
use stable lighter shades of their birthplace group's colour; shades identify
tiles and do not represent population magnitude. Area represents population.
The reusable [renderer option](../../local-modules/focalbi-rendering/chart-options.schema.json)
is enabled only for this chart and is recorded in `presentation.json`.

English use and birthplace by district (chart 156) uses
[language-birthplace.sql](./language-birthplace.sql), dataset 56, with one point per
district. X is `born_else / t_pop`: residents born outside Hong Kong, Mainland
China, Macao and Taiwan. Y is `ul_eng / SUM(the five ul_* counts)`: usual English
among residents aged 5+, excluding mute persons. These separate district totals
are not an individual-level joint distribution or a causal relationship. Original
language counts remain in dataset 37 and the source table. Region/District filters
select points without changing their denominators; no fixed correlation annotation
is displayed after filtering. The chart keeps ID 156 and its native filter scopes.

Create the virtual dataset with MCP, bind the existing chart through native API,
then apply MCP scatter settings and the `native_chart_overrides` in
`presentation.json`. The native `bubble_v2` display provides district identity,
three region colours and percentage tooltips. `max_bubble_size: 0` keeps point
sizes equal; population is additional hover context. Axes stay at 0–25% and 0–20%
under filters. Save the unfiltered browser-generated query context: this MCP's
fallback for `bubble_v2` otherwise omits X/Y metrics from `get_chart_data`.
Strip SQL comment lines before MCP `execute_sql`; its function validator can
misread the licence header's `Version` text. Dataset SQL retains the licence.
The full-width chart has a localized denominator note beneath it. Title,
description and note follow the selected locale; native axis, region and tooltip
labels are bilingual English/Traditional Chinese, as this chart type has no
locale adapter. Changing chart type removes old metric catalog fields; remove
only those obsolete entries before seeding the updated translations.

Apply [dashboard.css](./dashboard.css) through the native dashboard CSS setting.
Below 768px, the grid keeps a 1040px canvas with horizontal scrolling so native
chart text stays readable. Desktop row widths are unchanged; CSS-only stacking
does not recalculate Superset's chart canvas dimensions.

The map uses the official [2021 Census district boundaries from CSDI](https://data.gov.hk/en-data/dataset/hk-censtatd-census_geo-2021-population-census-by-dcd),
not present-day boundaries. [map.sql](./map.sql) joins the 18 boundary features to
the reviewed district summary by district code. All 18 source population values
match the census snapshot (total 7,411,945). Colour represents population counts,
not density: <200,000; 200,000–349,999; 350,000–499,999; 500,000–649,999; ≥650,000.
Fixed bins retain their meaning when filters change. Hover shows district name,
population, age 65+ share and median monthly household income. Map tooltips use
English and Chinese together; headings and caption follow the selected locale.

The saved map opts into `focalbi_disable_map_drag`, `focalbi_disable_map_zoom` and
`focalbi_hide_native_renderer_label` from the rendering module's
[chart options](../../local-modules/focalbi-rendering/chart-options.schema.json).
Dragging and zoom gestures cannot move the map. Native `autozoom` fits the full
map to its chart container on resize, with 20px padding. Tooltips and native
Region/District filters remain available. The native-renderer diagnostic is hidden.
Other charts retain their own settings. The flags are in `presentation.json` so
reapplying the map specification preserves this behavior.

Geometry is generalized by the official service at 0.0003 degrees and coordinates
are rounded to five decimal places for display. Do not use it to calculate land
area or population density. District geometry and census observations come from
the saved dataset. The map has no external tile or API-key dependency.

For a new installation, use MCP `create_virtual_dataset` with `map.sql` in database
1, schema `public`, then create a saved chart and attach it to Overview through
MCP. This MCP chart schema has no GeoJSON chart type; the native Explore settings
must supply `deck_geojson` and `map_form_data` from the presentation specification.
Use the native dashboard editor/API for row sizes and tab-preserving placement;
MCP `overview_layout` would flatten the six pages. Map dataset 55 and chart 181
are included in Region/District scopes; Source topic remains scoped only to 175.
Retain the existing tab/chart component IDs so their localization fields survive.
`map.sql` pins the reviewed release ID. A new census source release requires an
explicit review of that predicate, matching boundaries and cache invalidation.

## Prepare and provision

Commands run from the repository root. Python 3.10+ and Docker services are
required. Service startup and native MCP authentication are documented in the
[MCP operator guide](../../docs/admin_docs/configuration/focalbi-mcp.mdx).

1. Run `python local-data/hk-census-2021/prepare.py`. This downloads the source,
   validates headers, district codes, duplicate cells and additive totals, and
   writes ignored `snapshot/` CSVs plus `specifications.json` for MCP inputs.
   A source differing from the reviewed benchmarks requires an explicit review;
   do not disable the validation to accept a new release silently.
2. For a **new installation**, import the four generated CSVs through Superset's
   native CSV upload into database 1, schema `public`. The existing deployment
   already has these tables. Do not repeat the import: `upload.py` uses
   `already_exists=fail`, never replacement or append. If an operator has an
   authenticated session-cookie file, the equivalent native upload command is:

   ```powershell
   python local-data/hk-census-2021/upload.py --origin http://192.168.10.27:8088 --session-cookie <private-cookie-file>
   ```

   Keep credentials outside tracked files. The script uses explicit CSV types,
   obtains CSRF protection and records successful uploads in ignored `.runtime/`.
   MCP exposes no upload operation; database DML permissions remain disabled.
3. Use Codex's configured native `focalbi` MCP `create_virtual_dataset` for each
   dataset specification, then `generate_chart` with its saved dataset ID and
   `save_chart=true`. Before retrying a failed creation, inspect the native
   catalog to avoid duplicate resources. Record returned IDs and UUIDs in the
   resource manifest.
4. Create a separate draft with `generate_dashboard`. In Superset's native
   dashboard editor create the six manifest tabs; save them **before** calling
   `add_chart_to_existing_dashboard` with `target_tab`. The MCP tool falls back
   to the first tab if the requested tab does not exist. Edit card sizes and
   methodology text through the native editor.
5. Use `configure_dashboard` to create Region and District multiselects with
   whole-dashboard scopes, plus Source topic scoped only to the source table.
   Use stable keys: `region`, `district`, `source_topic`. In the native filter
   editor make District values dependent on Region. Empty selections mean All.
6. Complete display metadata through native dataset/Explore editors: dataset
   column labels, table number formats, source-table search and pagination. Raw
   table `ColumnRef.label` is not applied by this MCP converter. Native table
   ordering requires JSON-encoded `[column, ascending]` strings; specifications
   already encode them. Save and wait for completion before navigating away.
7. Validate before publishing to the authenticated Superset catalog. Publishing
   does not grant anonymous access. The FDS dashboard and existing website embed
   are independent; this workflow changes neither their bindings nor guest grants.

### Population pyramid source preparation

Run `python local-data/hk-census-2021/prepare_pyramid.py` after the reviewed district
snapshot exists. It downloads the official demographic CSV archive, extracts A204,
checks all 172 sex/single-age rows against Land totals, and reconciles each district's
sex totals and five original broad age bands with `DC_21C.CSV`. It produces the
ignored `snapshot/hk_census_2021_age_sex.csv` and maintained provenance file.

For a new installation, upload only this additional table:

```powershell
python local-data/hk-census-2021/upload.py --origin http://localhost:8088 --session-cookie <private-cookie-file> --tables age_sex
```

Upload uses `already_exists=fail`; do not repeat it on the provisioned deployment.
Physical dataset 57 and virtual dataset 58 are recorded in `resources.json`. Create
the virtual dataset through MCP from the explicit age/sex columns with
`census_year = 2021`, rebind chart 151 through native API, then apply its MCP and
native presentation specifications. Preserve its Region/District filter scope.
The uploader accepts an explicit table subset; omitting `--tables` retains the
original four-table workflow. Cookie files must match the supplied origin;
localhost sessions use CookieJar's `localhost.local` host convention.

Verify 648 district/age/sex rows, 18 displayed age bands and 7,411,945 positive
counts. Every displayed absolute share must equal the selected source counts
divided by selected district population; both sexes together sum to 100%.
Check oldest-at-top order, symmetric axes, district filtering and both Chinese
locales. Do not construct joint age/sex values from separate marginal totals.

## Domestic household composition by district

Chart 158 uses dataset 39 as a full-width horizontal 100% stacked bar chart.
Each of the 18 districts has eight household-composition segments. The source
`dhc_1`–`dhc_8` counts reconcile to the published `dh` household total in every
district. The denominator is domestic households, not people. Region/District
filters select bars without changing the retained districts' shares.

Apply the MCP `chart_overrides.158` configuration in
[presentation.json](./presentation.json), then its `native_chart_overrides.158`:
native `contributionMode=row` performs normalization, with fixed 0–100% bounds.
MCP's `stacked=true` alone produces counts, so the native normalization override
is required. Keep all eight categories and the existing filter scopes. The
paginated top legend retains full category names; hover shows segment shares.
Couple-based categories use related blue shades; other categories retain stable
distinct colours recorded under `household_composition.label_colors`.

The chart occupies its own row after household size. Titles, district names,
axis text and category labels use the existing English and two Chinese catalogs.
Verify all 144 shares against source counts, each bar summing to one, unchanged
shares after district filtering, both Chinese locales and the 30-day cache.

## District ethnicity heatmap

Chart 155 uses MCP's native Handlebars chart with dataset 59, one row per district.
[ethnicity-heatmap.sql](./ethnicity-heatmap.sql) retains all five ethnicity counts;
the four displayed columns are Filipino, Indonesian, White and Others. Each
percentage divides that group's count by the **district's total population**.
The fixed blue scale spans 0–12%; filters select rows without renormalizing shares
or changing colours. Counts and percentages appear on hover or keyboard focus.

The labelled 18-district baseline remains fixed under filters: 91.64% Chinese and
8.36% non-Chinese, out of 7,411,945 people. Marine is excluded. “Others” includes
people reporting more than one ethnicity. The original dataset 36 and source-cell
table retain all five groups, including Chinese.

Load [ethnicity-heatmap.html](./ethnicity-heatmap.html) into `handlebars_template`
using the MCP configuration recorded under `ethnicity_heatmap` in
[presentation.json](./presentation.json). The native sanitizer removes template
classes and CSS, so [ethnicity-heatmap.css](./ethnicity-heatmap.css) is appended to
dashboard 18's native CSS, scoped exclusively to `#chart-id-155`; preserve unrelated
rules. Its district/group colour rules are computed from this reviewed snapshot
on the same fixed scale as the SQL. After source corrections, regenerate these
rules from the SQL result and update the baseline before refreshing query caches.
Applying the template to another dashboard also requires its scoped CSS.

The title and description use both Chinese locale catalogs. Internal labels and
notes are bilingual English/Traditional Chinese; the current native Handlebars
adapter does not switch template text to Simplified Chinese. No renderer or
application configuration changes are required.

Verify 18 rows and 72 cells, each count against its source indicator, all five
groups summing to each district population, and shares using that denominator.
Check the visible legend, hover/focus, Region/District filtering, unchanged
filtered colours, Chinese titles and repeat-query cache hits.

## Domestic households by housing type

Chart 161 uses a 20-by-10 waffle grid, a part-to-whole chart distinct from the
dashboard's pies, bars and treemaps. Its five categories retain the published
`dh_pub`, `dh_s`, `dh_pri`, `dh_non` and `dh_tem` counts in dataset 41. Each square
represents approximately 0.5% of the selected districts' domestic households.
The legend and hover/keyboard tooltips show source counts and percentages
calculated from those counts, independently of square rounding.

Saved metrics under `dataset_metric_overrides.housing` in
[presentation.json](./presentation.json) aggregate after native Region/District
filters. A category receives the difference between rounded cumulative shares
times 200, in published category order. This guarantees 200 squares for nonempty
selections; square counts can differ from exact shares by less than one square.
Very small filtered categories may receive no square but remain in the legend.
`housing_cells_json` contains one `1` per allocated square plus a trailing null;
the Handlebars loop ignores the null. Source values and dataset SQL are unchanged.

Provision these saved metrics through native dataset API, preserving existing
metrics. Load [housing-waffle.hbs](./housing-waffle.hbs) into the MCP Handlebars
configuration `chart_overrides.161`. Apply the native renderer-label override
and append [housing-waffle.css](./housing-waffle.css) to dashboard CSS, preserving
other charts' styles. The marked block is also included in `dashboard.css`.
Keep the chart ID, dataset, geography scopes and 30-day cache. Save its unfiltered
browser-generated query context so MCP reads use the same aggregation and order.

The chart remains five columns wide, with height 76. A translated note below its
row explains square rounding. Its `housing-waffle-locale` ID and `lang` attribute
select explicit English, Traditional Chinese and Simplified Chinese template
labels. Native HTML sanitization remains enabled; CSS uses the safe prefixed IDs.
The presentation requires this dashboard CSS and note, including when reused.

Verify five legend rows, 200 equal squares in ten rows, stable category colours,
all three locales, hover/focus tooltips and geography filtering. The default view
totals 2,673,714 households: 807,304 public rental, 413,788 subsidised ownership,
1,415,740 private permanent, 13,134 non-domestic and 23,748 temporary. Their square
allocations are 60, 31, 106, 1 and 2. Central and Western plus Wan Chai must total
152,050 households while retaining 200 squares. Verify repeat-query cache hits.

## District household income comparison

Chart 159 combines income distribution and published median income in one
full-width card on Households and income. Each district has a seven-band, 100%
stacked bar with an overlaid amber median dot and a labelled HKD value on the right.
Bars use the top 0–100% axis; dots use the bottom HK$0–60,000 axis across the same
plot width. Dot positions do not identify income bands. Every segment's hover
and keyboard-focus tooltip includes the district, band, household count, share
and published median. Rows sort by median descending,
then district code. Seven fixed blue shades run from light for lower income to
dark for higher income; colour always identifies the same band under filters.
Chart 160's saved definition is retained but detached from this dashboard.

[income-comparison.sql](./income-comparison.sql), dataset 60, joins official
`dhi_1`–`dhi_7`, `dh` and `ma_hh` observations for the reviewed release. All cover
domestic households, including economically inactive households. Band shares are
`100 * band_count / dh`; the median is the published `ma_hh`, never estimated from
the seven bands or averaged across districts. Region/District filters select
rows without changing district denominators or median values. Marine and the
separate Land reference are excluded.

The `income_comparison` block in [presentation.json](./presentation.json) records
the MCP raw Handlebars configuration, file bindings, note and dimensions. Load
[income-comparison.hbs](./income-comparison.hbs) as `handlebars_template`, rebind
chart 159 to dataset 60 through native API, and apply its native sort override.
Save the unfiltered browser-generated query context for MCP chart-data queries.
The scoped [income-comparison.css](./income-comparison.css) block is included in
[dashboard.css](./dashboard.css); preserve other dashboard styles when applying it.
Keep the localized note directly below the chart and remove chart 160 from this
dashboard's layout, membership and chart/filter metadata without deleting it.

HTML sanitization remains enabled. Native Handlebars strips classes and inline
styles, so the template uses unique safe IDs; the sanitizer prefixes them with
`user-content-`. Dashboard CSS sets widths and dot positions from numeric `title`
percentages using typed CSS `attr()`. This requires a browser supporting typed
`attr()`; verified in Chromium. Older browsers are not validated. This presentation
depends on dashboard CSS and is not styled in standalone Explore. At narrow widths
the 940px chart scrolls horizontally instead of compressing district labels.

Title, description, district names, panel headings, tooltips and note support
English, Traditional Chinese and Simplified Chinese. Explicit template labels
are selected by CSS using the translated note's `ci-income-locale` ID and `lang`
attribute. Keep that marker in all three note translations; the native Handlebars
adapter does not translate template text. Queries and numeric values stay unchanged.

Verify 18 unique rows and 162 source observations, seven counts summing to each
district's household count and 2,673,714 households overall. Check descending
medians (Central and Western HK$45,040; Wan Chai HK$45,000), exact percentage
widths, shared row centres, overlaid dot positions, top/bottom axis placement,
median values in every segment's hover/keyboard tooltip and all three
locales. Selecting those two districts must retain their published medians and
shares. Repeat chart-data requests must hit the existing 30-day query cache.

## Household income comparisons and cumulative curves

Two additional full-width charts follow the existing income comparison on
Households and income. Both use Region/District filters; Source topic is excluded.
Their definitions, dimensions and native overrides are in
[presentation.json](./presentation.json), with IDs in [resources.json](./resources.json).

- **Chart 182 / dataset 61: household income dumbbell.**
  [household-income-dumbbell.sql](./household-income-dumbbell.sql) reads published
  district medians `ma_hh` and `ma_econhh`. Light blue denotes all domestic
  households, dark blue the economically active subset. The connector compares
  overlapping populations, not change over time or an employment effect.
  All 18 district pairs use one HK$0–70,000 axis and sort by absolute difference.
  Filtering selects pairs without averaging medians. Hover or keyboard focus
  shows each published value; the right column shows the difference in HKD.
- **Chart 183 / dataset 62: cumulative income curves.**
  [household-income-cumulative.sql](./household-income-cumulative.sql) retains
  district-level counts at six published thresholds: HK$6,000, 10,000, 20,000,
  30,000, 40,000 and 60,000. Each regional point is
  `SUM(households_below_threshold) / SUM(household_count)` after filters, grouped
  by region and threshold. A district contributes its denominator once per point.
  The native line chart has markers, a numeric HKD axis and a fixed 0–100% share
  axis. Connecting lines guide reading; they do not estimate values within bands.
  The open-ended top band is not assigned an invented upper threshold.

The dumbbell uses MCP's supported Handlebars chart. Load
[household-income-dumbbell.hbs](./household-income-dumbbell.hbs) into the recorded
MCP config's `handlebars_template`, and append
[household-income-dumbbell.css](./household-income-dumbbell.css) to native dashboard
CSS while preserving other sections. Source values drive positions through CSS
typed `attr()` percentages; use a browser supporting this feature. The template
is sanitized and contains no executable script. The localized
`MARKDOWN-HOUSEHOLD-ADDITIONS-NOTE` supplies the `hh-income-locale` language marker
for English/Traditional/Simplified Chinese text. Keep that note with the chart.
Both chart titles and descriptions support both Chinese locales. Native line
axis/region labels remain English under the current localization adapter.

Verify 36 published medians, their pixel positions and 18 connecting lengths.
Check all 18 unfiltered regional points against source counts and recompute
selected-district denominators. Below HK$20,000, shares are 31.22099% for Hong Kong
Island, 42.81010% for Kowloon and 36.91811% for New Territories. Selecting Central
and Western plus Wan Chai must show two pairs and one recomputed regional curve;
selecting Kowloon must show five pairs and the unchanged Kowloon curve. Also check
both Chinese titles, dumbbell labels/tooltips, empty states, and cached responses.

## Household tenure sunburst

Chart 162 uses native `sunburst_v2` with dataset 63 from
[tenure-sunburst.sql](./tenure-sunburst.sql). The inner ring has three derived
display groups: owner-occupied, rented and other arrangements. The outer ring
retains all six published tenure categories. “Shared tenancy” abbreviates
co-tenant/main tenant/sub-tenant; the full source category is retained in the
dataset. These are household counts, not population counts. No total rows are
included alongside detail rows.

Owner-occupied uses blue shades, rented teal shades and other arrangements amber
shades. Exact stable label colours, native chart settings and the methodology
note are recorded under `tenure_sunburst` and `native_chart_overrides.162` in
[presentation.json](./presentation.json). Tooltip values include household count,
percentage of all selected households and percentage of the parent group.
Labels below 2% may be hidden, but their segments and tooltips remain available.

MCP creates the dataset and manages the saved chart and dashboard colours. Its
current chart-type schema lacks sunburst, so apply the native override through
Superset Explore/API. Keep chart ID/UUID and Region/District scope unchanged.
Dataset 42 remains available for the original distribution. Chart 162 and dataset
63 retain the 30-day cache policy. Titles and the note support both Chinese
locales; native ring labels remain English under the current locale adapter.

Verify three parents, six leaves and 2,673,714 households across all 18 districts.
Every parent must equal the sum of its children. Compare the six leaf counts
against `dh_ocm`, `dh_ocwm`, `dh_st`, `dh_co`, `dh_rf` and `dh_emp` in the source
snapshot. Wan Chai selection must total 63,128 households with unchanged category
colours. Check tooltips, both Chinese titles and repeated-query cache hits.

## Education and work chart variety

This tab preserves six chart IDs and uses the layout recorded under
`layout_rows` and `education_work_variety` in [presentation.json](./presentation.json):

| Chart | Display and statistical meaning |
| --- | --- |
| 165 | Sankey: region of residence → highest educational level attended, for residents aged 15+. The 21 links classify one population; they are not movements, education transitions or career paths. |
| 166 | Existing employment-status donut, retaining four published categories. |
| 167 | Equal-size district scatter: degree-course attendance share among residents aged 15+ versus managers/professionals/associate-professionals share among workers. |
| 168 | Treemap: all 11 industry categories, area proportional to working residents. Hover retains full category labels and counts. These are residents' industries, not jobs located in the district. |
| 169 | Existing ordered employment-income-band bars; these retain their original exclusions of foreign domestic helpers and unpaid family workers. |
| 170 | Horizontal dot plot of published district labour force participation rates. A labelled fixed 50–70% detail axis makes district differences visible; points do not encode magnitude as bar length. |

Scatter dataset 64 is defined in
[education-occupation.sql](./education-occupation.sql). It contains 18 rows with
both numerators and their distinct denominators. “Degree course” means highest
level **attended**, not degree completion. The unweighted district Pearson
correlation is approximately 0.984; it is a contextual association between two
different aggregate populations, not evidence about individual outcomes or
causation. Each point retains district identity, region colour and working
population in its tooltip. The original occupation distribution remains available
in dataset 46 and the source-cell table.

MCP owns the correlation dataset, supported scatter configurations and saved
chart metadata. Apply `native_chart_overrides` after MCP saves: native Sankey and
treemap are outside the current MCP chart schema; `bubble_v2` supplies district
identity and region grouping, and horizontal `echarts_timeseries_scatter` supplies
the dot plot. No application, MCP or rendering-module modifications are needed.
Retain the source/methodology note `MARKDOWN-CENSUS-EDUCATION-VARIETY-NOTE`.
Titles, descriptions and that note support both Chinese locales. The correlation
scatter has bilingual English/Traditional Chinese axes and district labels;
other native internal labels remain English under the current locale adapter.

Verification must compare all 21 Sankey links, 18 scatter coordinates, 11 industry
counts and 18 district rates with the reviewed census snapshot. Check that two
districts on Hong Kong Island produce seven Sankey links, two scatter points,
11 recomputed industry totals and two unchanged participation rates. All changed
charts keep Region/District filters and the 30-day cache policy. Source topic
remains restricted to the source-cell table. Verify both Chinese titles and
repeat-query cache hits after changes.

## Mobility and sources chart variety

Charts 171–174 use four complementary views. Chart 175 remains the published
source-cell table. IDs, Region/District scopes and the source-topic filter are
preserved; geography filters refer to **current residence**.

| Chart | View | Meaning |
| --- | --- | --- |
| 171 | Treemap | Eight published workplace categories; area represents workers |
| 172 | Box plot | Distribution of district local-work and local-study rates |
| 173 | Heatmap | Four residence-change shares within each of the 18 districts |
| 174 | Sankey | Previous broad area to current region for internal migrants aged 5+ |

[mobility-local-rates.sql](./mobility-local-rates.sql), dataset 65, supplies one
observation per district. Work rate is `plw_same / SUM(eight plw counts)`; study
rate is `pls_same / SUM(five study counts)`. Work at home is a separate workplace
category and is excluded from the local-work numerator. Students are those taking
full-time courses in Hong Kong institutions. Both use the official district /
new-town definition. The populations are distinct; this is not an individual
journey comparison. Boxes show district quartiles and median, with min/max
whiskers. Districts have equal weight; a one-district selection collapses each
box to one rate. Across all 18 districts, medians are 14.72% for local work and
50.30% for local study; the ranges are 8.03–33.13% and 36.86–69.89% respectively.

[mobility-residence.sql](./mobility-residence.sql), dataset 66, groups the seven
published `pm_*` **person counts** into four statuses. Their sum is the district
population aged 5+; each cell divides its status count by this sum. Rows therefore
sum to 100% before display rounding. The native heatmap uses a fixed 0–100% blue
scale, percentage labels and no rank normalization. The Sankey retains dataset
52's four published previous-area categories. Prefixes `Previous:` and `Current:`
keep graph nodes distinct. New towns and other New Territories / Marine areas
are source classifications; no exact district-to-district flow is inferred.

MCP creates the datasets, saves chart names and sets dashboard label colours.
These four native chart types require the saved `native_chart_overrides` in
[presentation.json](./presentation.json) through Superset Explore/API. Apply them
after MCP saves. Preserve the source table, existing methodology and other tabs
when applying the Mobility layout and localized note. Titles and notes have both
Chinese locales; some native internal labels remain English, while box labels
are bilingual. This workflow does not modify rendering/localization modules.

Verification: 3,680,407 workers, 1,063,445 students, 7,182,991 residents aged 5+
and 796,456 internal migrants match the reviewed source cells. Check all eight
treemap counts, 12 Sankey links, 72 heatmap cells and box statistics; repeat with
Central and Western plus Wan Chai selected. Check both Chinese title sets,
percentage labels, tooltips, unchanged source table/filter scopes and 30-day
query-cache hits. Datasets 50 and 51 remain available for the former charts.

## Content languages

[localization.json](./localization.json) contains the English-keyed Traditional
Chinese (`zh-Hant`) and Simplified Chinese (`zh-Hans`) display catalogs for the
same dashboard, its 33 active charts, the retained chart 160, the original 24 analytical datasets and pyramid dataset 58. Dataset 56's
native scatter labels are bilingual, as described above. It covers titles, six tabs,
filters, introduction/methodology, table and metric labels, district/region/sex
names, category and topic dictionaries, units, status text and source notes.
Official bilingual indicator/geography metadata and notes from the reviewed
snapshot supply Traditional Chinese statistical terminology. Simplified entries
are stored explicitly in the catalog, not converted at viewer runtime.

Apply from the repository root using an authorized native session:

```powershell
python local-modules/focalbi-localization/scripts/seed.py local-data/hk-census-2021/localization.json --origin http://localhost:8088 --cookie local-modules/focalbi-localization/.runtime/admin-cookie.json
```

The existing [localization module](../../local-modules/focalbi-localization/README.md)
owns authoring and the SDK locale bridge. No duplicate dashboard, data rewrite,
frontend rebuild or cache reset is needed. Raw keys, numeric values, source URLs,
indicator codes, queries and native CSV exports retain their original values.
Some native Superset UI messages, such as `Filters out of scope`, remain in
the application UI language; they are not resource-catalog fields.
Catalog saves are separate from native dashboard saves; changed source text
requires translation review. Apply this fixture only to its census resources.

Verify both Chinese locales on OPEN.GOV across all six tabs, including category
labels and source-table notes. Direct bridge switching must preserve the iframe
and active view without chart queries; host page navigation is a separate lifecycle.

## Query-result caching

The 32 analytical datasets (31–53, 55, 56, 58–64), age/sex physical dataset 57,
and 33 dashboard charts (145–159, 161–175 and 181–183), plus retained chart 160, use
`cache_timeout=2592000` seconds (30 days). This is a per-resource setting;
the shared database/global cache defaults and guest-token endpoint are unchanged.
Each distinct filter/query combination has its own cache entry. Redis eviction
or a cache reset can remove results before their timeout. A timeout of zero
falls back to defaults in this checkout and must not be used for this policy.

Warm the default views by visiting all six tabs on the embedded OPEN.GOV page.
Verify chart-data responses report `is_cached: true` on repeat requests and
`cache_timeout: 2592000`. This accelerates query results, not the host page or
JavaScript startup. New filter combinations are populated on their first query.

After source corrections, force-refresh affected chart/filter views to replace
their cached results; warming only default views does not invalidate previously
cached filtered views. Before publishing corrected data, an operator must also
invalidate affected census query keys or wait for their expiration. Do not flush
the shared Redis database, which serves other dashboards. Chart/query-definition
changes can generate different keys; verify the new views rather than assuming
old entries were removed. Rewarm all six default tabs after refresh or eviction.

## Normal editing and metric rules

Edit or add/remove charts using native Superset Explore and Edit dashboard. No
renderer JSON, viewer data source binding or application code change is required.
Both rendering engines receive the same native chart data. New visual types must
be supported by the rendering module's registry or its explicit native fallback.
The district map uses the native fallback, including the existing renderer label.

- Population, households and working population sum district counts.
- Elderly share is `SUM(age 65+) / SUM(population)`, not a mean of district rates.
- Medians, averages and published rates remain district indicators; a district
  bar uses `MAX` over its single published observation. Do not sum medians.
- Whole Hong Kong benchmarks (7,413,070 people; 2,674,161 households) include
  different coverage and stay fixed in the introductory note. District totals
  exclude Marine and the separate Land reference row.
- `-` is a published nil; `..` is not applicable; `N.A.` is not available.
  Original tokens and status are retained beside numeric values. Published nil
  does not establish the absence of sampling uncertainty.
- Marital status/education, language, employment income and mobility have
  different statistical populations. Their definitions are retained in dataset
  descriptions and source-cell notes. Geography filters refer to residence.
- Districts use 2021 boundaries. This is a census snapshot, not a current
  population estimate or a multi-year trend.

## Verify and remove

Run `python -m unittest discover -s local-data/hk-census-2021 -p 'test_*.py' -v`.
Run preparation first to include the source-snapshot test; without the snapshot
that test is explicitly skipped. Local checks cover symbols, units, count
reconciliation, source corruption, reference exclusion and native specifications.

Use MCP to query all saved charts and verify 7,411,945 people, 2,673,714 households,
3,680,407 working people and 19.5825% elderly share. Central and Western plus
Wan Chai have 402,648 people. A no-match query returns the MCP `NoData` response.
`get_chart_data(limit=...)` reports the limited returned row count; it is not an
independent completeness check. Verify source-cell completeness through native
chart-data results/export and physical-table counts.

In the browser check all six tabs, geography selection/cascade, source-topic
scope, tooltips, sorting, table pagination/search/CSV export and both engines.
Renderer switching must preserve the applied view without a new query. Temporary
screenshots, exports and probe reports belong in ignored `snapshot/` or `.runtime/`.
No application build or migration is needed for this data-only workflow.

An observed rendering limitation affects previously mounted tables on inactive
tabs: switching engines elsewhere can leave their sizing container hidden when
returning. Switch Renderer again with the affected tab active to restore the table
without another query. This workflow does not modify the rendering overlay.
The two district tables also show a native row-limit warning at exactly 18 rows;
the verified dataset contains exactly 18 districts, so these results are complete.

For rollback, export dashboard 18 from Superset, then remove **only** the manifest's
dashboard/charts/analytical datasets through native management screens after
checking UUID ownership and use by other dashboards. Remove the four physical
dataset registrations last. A database administrator may drop the four exact
manifest tables after confirming no remaining dependencies; do not enable DML
in the shared Superset connection to perform cleanup. Preserve the source archive
and provenance as required. Existing FDS resources and the rendering overlay are
not census-owned and must remain intact.

# Hong Kong Census 2021 workflow

This workflow prepares official **published district aggregates** and creates a
native Superset dashboard. It introduces no Superset, MCP or renderer features.
Dashboard 18 is **Hong Kong Census 2021 - People, Households and Districts**;
its UUID, charts and datasets are recorded in [resources.json](./resources.json).
Open the [published LAN dashboard](http://192.168.10.27:8088/superset/dashboard/18/)
with your Superset login. Publication does not grant anonymous access.

## Source and tables

The source is the Census and Statistics Department's
[2021 population and household district profile](https://data.gov.hk/en-data/dataset/hk-censtatd-census21c-d5212109).
The reviewed resource was updated on 27 April 2026; the reference year remains
2021. `prepare.py` downloads the official multi-geography archive and reads only
`DC_21C.CSV`. Source hashes, symbols and benchmarks are in
[provenance.json](./provenance.json).

Four physical tables reside in database 1, schema `public`:

| Table | Grain |
| --- | --- |
| `hk_census_2021_release` | One reviewed source release |
| `hk_census_2021_geography` | 18 districts and one separate Land reference |
| `hk_census_2021_indicator` | 205 source fields, bilingual labels, units and notes |
| `hk_census_2021_cell` | Release × geography × indicator; 3,895 published cells |

The 23 analytical virtual datasets select only the 18 land districts. The source
table chart contains **3,690 cells**, not individual census respondents. The
summary dataset has one row per district. Each distribution dataset represents
one statistical population; it does not manufacture age × ethnicity × income
cross-tabulations from unrelated marginal totals.

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

## Normal editing and metric rules

Edit or add/remove charts using native Superset Explore and Edit dashboard. No
renderer JSON, viewer data source binding or application code change is required.
Both rendering engines receive the same native chart data. New visual types must
be supported by the rendering module's registry or its explicit native fallback.

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

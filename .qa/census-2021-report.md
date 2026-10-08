# Hong Kong Census 2021 verification

Verified 5 October 2026 HKT. Scope: official district data preparation and native
Superset resources; no Superset, MCP, website or rendering-module source changes.

## Resources and data

- Published dashboard 18, UUID `4609843d-3896-4028-bce3-424c86f77101`, contains
  31 saved charts in six native tabs. Four physical tables and 23 analytical
  virtual datasets are recorded with ownership UUIDs in
  [resources.json](../local-data/hk-census-2021/resources.json).
- Official `DC_21C.CSV` contains 205 indicators and 19 geographies: 3,895 cells.
  Analytics exclude the separate Land reference; 18 districts give 3,690 cells.
  Source hashes, release date, symbols and definitions are retained in
  [provenance.json](../local-data/hk-census-2021/provenance.json).
- Reconciled district totals: 7,411,945 people, 2,673,714 domestic households,
  3,680,407 working people and 1,451,444 people aged 65+ (19.582498% share).
  Published medians and rates remain district observations, not false aggregates.

## Native MCP and local checks

- Creation/configuration used Codex's configured FocalBI MCP. A fresh native
  Codex app-server MCP runtime discovered 25 tools and queried all 31 charts.
  KPI results and the Central and Western/Wan Chai total of 402,648 passed;
  a no-match query returned the native MCP `NoData` response.
- Native CSV upload was used because MCP exposes no ingestion operation;
  all four uploads returned HTTP 201. No DML permission was enabled. Native
  editors supplied layout, cascading filters, display labels and publication.
- Four standalone source/contract tests pass, including corruption rejection.
  Scoped Ruff lint/format and MyPy checks pass for all three new Python files;
  `git diff --check` passes. No unrelated full application build was required.
- The active conversation's short-lived MCP credential expired during the task.
  The normal headers helper exceeded the runtime's ten-second startup budget
  under load. Verification pre-minted with that installed helper and supplied
  the token only to an ephemeral Codex MCP runtime's environment. No credentials
  were persisted, and the global helper/configuration was not changed.

## Browser checks

- Headless Chrome rendered all six tabs. Active chart shapes, labels, formatting
  and tooltip behavior were checked in the existing baseline/fork engines.
  The sex tooltip showed Female: 4,030,315, 54.38%.
- Region cascades District options. Hong Kong Island exposes its four districts.
  Central and Western gives 235,953 people; adding Wan Chai gives 402,648.
  Clearing filters restores all districts and the benchmark KPIs.
- Source topic is excluded from the other 30 charts. Applying age groups updates
  only chart 175 to 90 source cells; the other chart queries do not run.
- Renderer switching issues zero new chart-data requests and preserves applied
  geography filters, active table sorting, page 2 and the `Yuen Long` search text.
- Native source CSV export contains all 3,690 cells with formal labels and
  reconciles with the KPI totals. Native Export YAML produced the dashboard,
  chart and dataset definitions; it does not include physical source data.
- Publication is saved. An anonymous request redirects to login; no census
  dashboard guest grant was added.
- FDS dashboard 16 metadata, filter configuration, chart definitions, UUID and
  change timestamp match the pre-task snapshot. The LAN website still embeds
  dashboard 16 and displays FDS's 53 records, HKD 72,002,518.80 and 19 departments.

## Limitations and evidence

- Switching engines while a previously mounted table is on an inactive tab can
  leave its sizing container hidden on return. Switching Renderer with that
  tab active restores it without a query. This observed rendering limitation is
  not fixed by the data-only workflow; complete cross-tab switch parity is not
  claimed. The native sticky-table sizing effect returns when its hidden header
  measures zero and does not depend on tab visibility.
- District tables warn when their 18-row limit is reached. Independent source
  and dataset counts confirm that all 18 districts are present.
- Native computer-use could not connect: `Computer Use native pipe is
  unavailable` / Windows error 2. Browser verification used Playwright with
  headless Chrome, not native computer-use.
- Local screenshots: [overview](../local-data/hk-census-2021/snapshot/overview-final.png),
  [people](../local-data/hk-census-2021/snapshot/people.png),
  [baseline people](../local-data/hk-census-2021/snapshot/people-baseline.png),
  [housing](../local-data/hk-census-2021/snapshot/housing.png),
  [mobility and sources](../local-data/hk-census-2021/snapshot/mobility-sources-final.png).
  Exports and native probe reports are in ignored `snapshot/` and `.runtime/`.

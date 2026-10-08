# FocalBI native rendering overlay verification

Scope: presentation-only migration under `local-modules/focalbi-rendering`, native
company comparison resources, and the existing website's operator-controlled embed
binding. No Superset/MCP core source changes.

## Verified

- Native bundle builds; 357 baseline files match their recorded hashes. Fourteen
  native load/filter/request/query-builder and wrapped source files retain their
  before/after hashes in `dist/native-source-integrity.json`.
- Module-owned frontend type checks and Python lint pass. Five presentation unit
  tests, two documentation-ownership tests and two website token tests pass.
- The embedded LAN dashboard renders eight charts. FDS gives 53 records,
  HKD 72,002,518.80 and 19 department relationships. FDS plus OPM gives 150 records,
  HKD 183,079,390.79, 52 relationships and 19.8921% of eligible A/Minor value.
- Applied selection titles, comparison colors, eligible Top 10 population,
  annual fill order, native year scopes and formal source-table dates pass.
  A general transform adapter makes native single-series categorical-bar value
  controls honor ascending/descending display order without changing ranked rows.
- Baseline/fork options and results match. Engine switching adds no queries and
  preserves native table sorting/pagination and legend selections. Clearing the
  required company control disables Apply and retains previously applied data.
- A separate native dataset with different column names renders five pies without
  a module dashboard definition. Native chart addition/removal renders six/five
  charts without module edits. Presentation metadata survives native Save/reload;
  native Discard restores it. Temporary fixture resources were cleaned up.
- Website tokens authorize one configured resource; untrusted origins and visitor
  resource overrides are rejected. Native chart-data rejects the unrelated dataset
  with HTTP 403. Automatic native SDK renewal succeeds beyond one token lifetime.
- Original dashboard 11, its eight charts, and dataset 22 match the saved backup.
  Uninstall with retained resources restores the original embed and native image
  renderers. Reactivation restores the company dashboard and renderer overlay.
- Retired custom source dashboards/charts/dataset were removed through native
  deletion commands after ownership/sharing validation. Original resources remain.

## Evidence

Reports and screenshots are local, ignored artifacts under
`local-modules/focalbi-rendering/test-results/`: `native-browser.json`,
`native-company-multi.png`, `native-editor.json`, `native-generic.png`,
`native-layout-5.json`, `native-layout-6.json`, `native-access.json`,
`native-renewal.json`, `native-original-unchanged.json`, `native-rollback.json`,
`native-rollback.png`, and `native-activation.json`/`.png`.
Deployment and removal commands are in the module README.

## Limits

- Computer Use could not run: the native connector pipe was unavailable, and
  `cua.getState()` returned no browsers; Chrome creation reported unavailable.
  Browser evidence above comes from automated Chrome tests, not Computer Use.
- Reused native dependencies report 3,087 TypeScript diagnostics separately from
  module-owned checks. A full repository type-check pass is not claimed. The host
  pre-commit executable is unavailable; focused lint/build/tests were run directly.
- This developer bundle is unminified. Production optimization/performance checks
  remain separate from this LAN deployment.
- Dashboard-wide atomic loading, source completeness guards, custom aggregation
  and custom filter/query APIs were deliberately removed. Native per-chart request,
  loading/error, row-limit, filter and access semantics apply. The module makes no
  stronger guarantees than native Superset for those stages.
- MCP dataset-info has an existing result-wrapper error; its chart-data wrapper
  lacks the form-data context used by native Jinja filter_values. Templated chart
  calculations were validated through the native dashboard/chart-data API.

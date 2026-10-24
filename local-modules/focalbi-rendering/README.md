# FocalBI native rendering overlay

The module adds optional renderer controls and presentation enhancements to
native Superset dashboards. Create/edit dashboards normally: adding, removing or
arranging charts needs no separate viewer definition. Filters, queries and access
controls remain native. [ARCHITECTURE.md](ARCHITECTURE.md) defines the boundary.

Copied renderers cover KPI, pie/donut, horizontal bar, mixed timeseries and table.
Other types retain native rendering with a fallback label. **FocalBI fork** is the
default. The renderer toolbar is hidden, and dashboards use the fork regardless
of an older saved renderer choice. Both implementations and the selector remain
available for testing.

Saved charts can opt into `focalbi_disable_map_drag`, `focalbi_disable_map_zoom` and
`focalbi_hide_native_renderer_label` (boolean flags in native chart params).
See [chart-options.schema.json](chart-options.schema.json) and the architecture
contract. Save flags through native chart authoring/API; the MCP chart converter
does not expose deck.gl settings. Rebuild the active combined localization bundle
after adapter changes; removing the flags restores defaults without a rebuild.

To show the selector again, open the browser console on the FocalBI origin (or
select its embedded frame as the console context), run
`localStorage.setItem("focalbi.rendererSelector", "true")`, and reload the page.
**Superset baseline** selects immutable copied renderers inside the same native
dashboard; this choice persists while the selector is enabled. To hide it again,
run `localStorage.removeItem("focalbi.rendererSelector")` and reload. This setting
is per browser and FocalBI origin; no rebuild or service restart is needed.

## Install and activate

Use the [Docker/MCP operator setup](../../docs/admin_docs/configuration/focalbi-mcp.mdx)
and snapshot-compatible superset-frontend dependencies. Node 22.22+ and Python
are required. Install supplemental pinned packages, then build:

```powershell
cd local-modules/focalbi-rendering
npm.cmd ci --legacy-peer-deps --ignore-scripts
node --max-old-space-size=12288 --experimental-strip-types scripts/build.ts
```

Copy [settings.example.json](settings.example.json) to `.runtime/settings.json`;
set the website path, approved native embedding UUID and rollback UUID.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/activate.ps1 -SkipBuild
```

Only the web service's compiled frontend assets are mounted. No Python extension
is registered; renderer activation does not restart MCP/workers. The reference
website helper starts its existing server/focalbi-demo.ts and persists its approved
UUID in ignored local configuration. Other websites use their normal native SDK
and guest-token backend; no renderer-specific token service is needed.

When [localization](../focalbi-localization/README.md) is active, rendering activation
builds its combined frontend and retains the localization backend. Removing
rendering builds localization-only assets before restoring the website target.
Removing localization retains rendering. Both modules leave native queries intact.

Build verifies baseline hashes and bundled dependency provenance, and checks native
source before/after in dist/native-source-integrity.json. Native buildQuery and
dashboard load/filter/request functions are reused unchanged. This developer build
disables minification to limit worker memory; optimize and performance-test a
production bundle deliberately before production deployment.

## Editing and native business settings

For native treemaps, save `focalbi_treemap_group_colors` in chart form data as a
mapping from exact first-level group names to six-digit hex colours, for example
`{"Hardware":"#1677a8","Services":"#218c6f"}`. Each group's descendants use
stable lighter shades of its colour. Names, values, queries and filter semantics
remain native. Both engines use this optional presentation setting; deleting it
restores native colours. Unconfigured groups retain native colours. The
[chart options schema](chart-options.schema.json) defines the saved contract.

Native dashboard edit/Save and Explore own charts, layout, filters, data sources,
metrics, formatting, exports and dates. The optional **Presentation** button in
dashboard edit mode binds dynamic titles, applicable colors and series layering.
Native Save/Discard/undo governs persistence. Dashboards without metadata work
normally. [presentation.schema.json](presentation.schema.json) documents settings.

Selection/comparison calculations belong in native saved datasets and metrics.
The company example uses trusted native Jinja SQL and the independent operator
ENABLE_TEMPLATE_PROCESSING flag. That setting contains no renderer import and
remains usable after rollback. Native dataset/guest permissions still apply.

The LAN page uses native dashboard 16, datasets 24/25 and eight charts. Company
defaults to FDS and is required. Category defaults to A/Minor globally; department
and theme apply globally; year affects all charts except the full annual timeline.
Original dashboard 11/dataset 22 remain the rollback target. The underlying public
SOA-QPS5 October 2026 snapshot is not refreshed automatically.

The annual chart uses native Mixed Time-series settings: awarded value as dark-blue
bars on the left HKD axis, share as an unfilled blue line on the right percentage
axis. Its secondary-behind-primary setting is disabled so the line draws over the
bars. Change these styles in Explore and save normally; no module rebuild is needed.

Datasets 24/25 reference a verified physical PostgreSQL snapshot through short native
SQL. This avoids reparsing inline source records before every cache lookup. The
[snapshot operator guide](../../local-data/soa-qps5/README.md) owns migration and
rollback commands; analytical data is independent of renderer installation/removal.

## Verify

```powershell
python -m unittest discover -s tests -v
node --experimental-strip-types tests/settings.test.ts
node --experimental-strip-types tests/category-sort.test.ts
node --experimental-strip-types tests/treemap-colors.test.ts
node --experimental-strip-types scripts/typecheck.ts
node --experimental-strip-types scripts/build.ts
python scripts/snapshot.py --verify
node --experimental-strip-types tests/native-browser.ts
```

The browser test requires the LAN website and approved company dashboard. Evidence
goes to ignored test-results; tokens are not printed. Prepare an unrelated native
test dataset/dashboard with `python tests/provision-generic.py`; native-editor.ts
uses an authorized administrator session via FOCALBI_TEST_SESSION and optional
FOCALBI_TEST_DASHBOARD_ID. Clean up only that fixture's ledger key afterward.
Run `tests/native-access.ts` while that unrelated fixture exists to check guest
dataset isolation. `tests/native-renewal.ts` checks automatic SDK token renewal.
After `uninstall.ps1 -KeepResources`, `tests/native-rollback.ts` verifies the
original website target and native image renderers; reactivate afterward.
Set `FOCALBI_TEST_MODE=active` for the same test to verify reactivation.
The website repository owns token-service tests. Module typecheck reports upstream
diagnostics separately and does not claim a full repository pass. Computer Use is
a separate check when its native connector is available.

Native MCP limitations in this revision: get_dataset_info has a to_mcp_result wrapper
error; get_chart_data does not populate the Flask form-data context used by Jinja
filter_values. Validate templated comparisons through native dashboard/chart-data
requests. MCP can create/configure the native resources; no MCP patch is installed.

## Rollback and removal

Preserve `.runtime/resources.json`, the optional cleanup ownership ledger.

```powershell
# Restore native assets/original website target and retain saved resources:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall.ps1 -KeepResources
# Full cleanup and optional folder removal:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall.ps1 -Username admin -PostId 1 -DeleteFolder
```

Cleanup checks identity, ownership and outside sharing, then uses native deletion
commands. Supply an assigned post as needed. Dataset 22 and original charts/dashboard
are never cleanup targets. Renamed/shared resources stop deletion for review.
Cleanup works after rollback: administrative inputs are copied into container
temporary files, without a module runtime mount. Removal restores native image
assets, preserves ordinary operator configuration and removes owned documentation
links before optional folder deletion. Reactivate retained resources with activate.ps1.

Review [provenance.json](provenance.json), [dependency-provenance.json](dependency-provenance.json),
[FORK_CHANGES.md](FORK_CHANGES.md), [LICENSE.txt](LICENSE.txt) and [NOTICE](NOTICE)
when changing copied sources or dependencies.

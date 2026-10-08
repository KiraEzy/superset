# Dashboard control localization verification

Verified 2026-10-05 against Superset 6.1.0. The change extends the removable
`local-modules/focalbi-localization/` extension and presentation overlay. Native
Superset/MCP source, rendering module source and immutable baseline files were
not edited. Existing unrelated work was retained.

## Delivered behavior

The selected content language controls filter headings, Apply/Clear buttons,
option counts, table search/page size/empty results, legend All/Invert buttons,
value sorting, donut totals and the renderer dropdown. English, Traditional
Chinese and Simplified Chinese have built-in messages; no resource catalog edits
are required. Relevant accessible labels follow the same language.

The adapters retain native callbacks, raw values, action identities and number
formatters. Custom control components, custom messages and custom legend titles
remain authoritative. Application navigation and editing retain Superset's UI
language. Free-text source records still require authored translations.

## Deployment and results

Both localization and rendering are active on
<http://192.168.10.27:3010/#focal-bi>. Dashboard 16 and embedding UUID
`52b05f1b-58a9-4e69-a879-a3e27af47cab` remain the website binding. Superset and
MCP containers are healthy. No dashboard/chart/dataset resources were created or
changed by this task. Translation storage retains eleven catalogs with a summed
revision count of seventeen; census definitions and catalogs were not changed.

| Check | Result and evidence |
| --- | --- |
| Presentation contracts | Fourteen frontend tests pass, including counts, formatted totals, custom fallbacks and raw legend selection identities. |
| Compilation overlay | Thirteen native/baseline/fork/module source surfaces pass syntax and compatibility checks. Incompatible anchors fail the build; source bytes remain unchanged. |
| Native-only deployment | Filter/table/sort controls, all three languages, page-size/search retention, empty search and native UI separation pass. [Result](../local-modules/focalbi-localization/test-results/controls-native.json). |
| Combined deployment | The same checks pass with rendering enabled. Unrelated census content exercises the same control adapters without definition changes. [Result](../local-modules/focalbi-localization/test-results/controls-combined.json). |
| LAN embed | All charts and the table load. Three languages, two independent simultaneous embeds, iframe/search retention and renderer switching pass. Zero locale-triggered chart-data requests, zero initial retries and no JavaScript errors. [Result](../local-modules/focalbi-localization/test-results/lan-embed.json). |
| Interaction preservation | Both engines retain raw query data, series, legend selection, annual zoom, date sorting and pagination. Localized native legend actions still select/invert correctly. Totals retain native formatting. Zero locale-triggered chart-data requests. [Result](../local-modules/focalbi-localization/test-results/preservation.json). |
| Metrics | LAN baseline retains HKD 72,002,518.80, 53 records and 19 department relationships. Multi-company checks retain HKD 183,079,390.79, 150 records and 52 relationships. |
| Guest access | Unauthorized resource reads and catalog writes remain denied; wrong-source bridge messages are ignored. See the LAN result. |
| Builds/types | Native-only and combined bundles and the extension package build successfully. Module-owned TypeScript check passes; 4,058 upstream diagnostics are recorded separately. |
| Integrity | Thirty protected native source hashes and 357 immutable baseline files pass. No tracked Superset/MCP core files changed. |
| Documentation | All 22 local links in the affected module/operator documentation and report index resolve. Contracts and coverage were reviewed against the adapters. |
| Removal | Localization removal retained rendering, translation data and website binding. Final deployment was restored to both modules. |

Reviewed screenshots: [Traditional Chinese embed](../local-modules/focalbi-localization/test-results/lan-embed-hant.png)
and [English embed](../local-modules/focalbi-localization/test-results/lan-embed-en.png).
An [unrelated resource screenshot](../local-modules/focalbi-localization/test-results/controls-unrelated.png)
is also available. Evidence and build logs are in ignored module directories.

## Documentation and limits

The [module README](../local-modules/focalbi-localization/README.md) documents
control coverage and verification commands. The
[architecture](../local-modules/focalbi-localization/ARCHITECTURE.md) records
per-viewer locale resolution, native contract preservation and the pinned host's
translation-import compatibility requirement. The
[operator guide](../docs/admin_docs/configuration/focalbi-localization.mdx)
documents the distinction between content/viewer controls and application UI.

Native computer-use still has no connected browser surface (`apps: []`,
`browsers: []`). Verification used automated local Chrome through Playwright;
native computer-use acceptance is unavailable and is not claimed passed.
Developer bundle size/CSS warnings and upstream TypeScript errors remain. This
task does not establish a full-repository type-check pass or translate every
source record. Native data/query paths and CSV exports remain unchanged.
